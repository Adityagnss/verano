"""teams: roles, invites, email verification, sign-in identities, token scopes, workspace keys, audit, limit

Existing per-project credentials are untouched: `provider_credentials.organization_key_id` is nullable and
empty for every existing row, so every key keeps working exactly as before.

Revision ID: 7c2d9e41ab63
Revises: e1a5c7d93b20
Create Date: 2026-11-07 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7c2d9e41ab63"
down_revision: str | None = "7b3e91c4a2d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = ("owner", "admin", "member", "viewer")
JSONB = postgresql.JSONB(astext_type=sa.Text())


def _id_columns() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    # roles: owner and member become owner, admin, member and viewer
    op.drop_constraint(op.f("ck_memberships_membership_role"), "memberships", type_="check")
    op.create_check_constraint(
        op.f("ck_memberships_membership_role"), "memberships", "role IN ('owner', 'admin', 'member', 'viewer')"
    )

    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("api_tokens", sa.Column("scope", sa.String(length=32), server_default="write", nullable=False))
    op.create_check_constraint(op.f("ck_api_tokens_token_scope"), "api_tokens", "scope IN ('read', 'write')")

    op.create_table(
        "invites",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("emailed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *_id_columns(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["accepted_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_invites"),
        sa.UniqueConstraint("token_hash", name="uq_invites_token_hash"),
        sa.CheckConstraint("role IN ('owner', 'admin', 'member', 'viewer')", name="ck_invites_invite_role"),
    )
    op.create_index("ix_invites_organization_id_id", "invites", ["organization_id", "id"])
    op.create_index("ix_invites_organization_id_email", "invites", ["organization_id", "email"])

    op.create_table(
        "email_verifications",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        *_id_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_email_verifications"),
        sa.UniqueConstraint("token_hash", name="uq_email_verifications_token_hash"),
    )
    op.create_index("ix_email_verifications_user_id", "email_verifications", ["user_id"])

    op.create_table(
        "external_identities",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        *_id_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_external_identities"),
    )
    op.create_index(
        "ix_external_identities_provider_subject", "external_identities", ["provider", "subject"], unique=True
    )
    op.create_index("ix_external_identities_user_id", "external_identities", ["user_id"])

    op.create_table(
        "organization_keys",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("encrypted_key", sa.LargeBinary(), nullable=False),
        sa.Column("key_last4", sa.String(length=4), nullable=True),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("rpm_limit", sa.Integer(), nullable=True),
        sa.Column("tpm_limit", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        *_id_columns(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_organization_keys"),
    )
    op.create_index("ix_organization_keys_organization_id_id", "organization_keys", ["organization_id", "id"])

    op.add_column("provider_credentials", sa.Column("organization_key_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_provider_credentials_organization_key_id_organization_keys",
        "provider_credentials",
        "organization_keys",
        ["organization_key_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_provider_credentials_organization_key_id", "provider_credentials", ["organization_key_id"])

    op.create_table(
        "organization_settings",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("monthly_spend_limit", sa.Numeric(18, 2), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("organization_id", name="pk_organization_settings"),
    )

    op.create_table(
        "audit_events",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_name", sa.String(length=320), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", JSONB, nullable=False),
        *_id_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index("ix_audit_events_organization_id_id", "audit_events", ["organization_id", "id"])
    op.create_index("ix_audit_events_organization_id_action_id", "audit_events", ["organization_id", "action", "id"])
    op.create_index(
        "ix_audit_events_organization_id_actor_id_id", "audit_events", ["organization_id", "actor_id", "id"]
    )
    op.create_index("ix_audit_events_organization_id_created_at", "audit_events", ["organization_id", "created_at"])
    # append-only, even for code that bypasses the audit module
    op.execute(
        """
        CREATE FUNCTION audit_events_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'The audit log can only be added to, not changed or deleted.';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER audit_events_no_change BEFORE UPDATE OR DELETE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_change ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS audit_events_append_only()")
    op.drop_table("audit_events")
    op.drop_table("organization_settings")
    op.drop_index("ix_provider_credentials_organization_key_id", table_name="provider_credentials")
    op.drop_constraint(
        "fk_provider_credentials_organization_key_id_organization_keys", "provider_credentials", type_="foreignkey"
    )
    op.drop_column("provider_credentials", "organization_key_id")
    op.drop_table("organization_keys")
    op.drop_table("external_identities")
    op.drop_table("email_verifications")
    op.drop_table("invites")
    op.drop_constraint(op.f("ck_api_tokens_token_scope"), "api_tokens", type_="check")
    op.drop_column("api_tokens", "scope")
    op.drop_column("users", "email_verified_at")
    op.execute("UPDATE memberships SET role = 'member' WHERE role IN ('admin', 'viewer')")
    op.drop_constraint(op.f("ck_memberships_membership_role"), "memberships", type_="check")
    op.create_check_constraint(op.f("ck_memberships_membership_role"), "memberships", "role IN ('owner', 'member')")
