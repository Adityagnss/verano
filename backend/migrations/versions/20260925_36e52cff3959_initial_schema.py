"""initial schema

Revision ID: 36e52cff3959
Revises:
Create Date: 2026-09-25 13:25:11.101367
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "36e52cff3959"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_personal", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
    )
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "memberships",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("owner", "member", name="membership_role", native_enum=False, create_constraint=True, length=32),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_memberships_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_memberships_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memberships")),
    )
    op.create_index(
        op.f("ix_memberships_organization_id_user_id"), "memberships", ["organization_id", "user_id"], unique=True
    )
    op.create_index(op.f("ix_memberships_user_id"), "memberships", ["user_id"], unique=False)
    op.create_table(
        "projects",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_projects_created_by_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_projects_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_index(op.f("ix_projects_organization_id_id"), "projects", ["organization_id", "id"], unique=False)
    op.create_table(
        "refresh_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_refresh_tokens_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index(op.f("ix_refresh_tokens_family_id"), "refresh_tokens", ["family_id"], unique=False)
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)
    op.create_table(
        "datasets",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_datasets_project_id_projects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_datasets")),
    )
    op.create_index(op.f("ix_datasets_project_id_id"), "datasets", ["project_id", "id"], unique=False)
    op.create_table(
        "evaluator_sets",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_evaluator_sets_project_id_projects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluator_sets")),
    )
    op.create_index(op.f("ix_evaluator_sets_project_id_id"), "evaluator_sets", ["project_id", "id"], unique=False)
    op.create_table(
        "input_files",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "golden_set",
                "raw_inputs",
                "reference_document",
                name="input_file_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "uploaded",
                "parsed",
                "failed",
                name="input_file_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=200), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=1000), nullable=False),
        sa.Column("sheet_name", sa.String(length=200), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("column_mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("validation_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_input_files_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_input_files_project_id_projects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_input_files")),
    )
    op.create_index(op.f("ix_input_files_project_id_id"), "input_files", ["project_id", "id"], unique=False)
    op.create_table(
        "prompts",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_prompts_project_id_projects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prompts")),
    )
    op.create_index(op.f("ix_prompts_project_id_id"), "prompts", ["project_id", "id"], unique=False)
    op.create_table(
        "provider_credentials",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("encrypted_key", sa.LargeBinary(), nullable=True),
        sa.Column("key_last4", sa.String(length=4), nullable=True),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column(
            "status",
            sa.Enum("valid", "invalid", name="credential_status", native_enum=False, create_constraint=True, length=32),
            nullable=False,
        ),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("rpm_limit", sa.Integer(), nullable=True),
        sa.Column("tpm_limit", sa.Integer(), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_provider_credentials_created_by_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_provider_credentials_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_credentials")),
    )
    op.create_index(
        op.f("ix_provider_credentials_project_id_id"), "provider_credentials", ["project_id", "id"], unique=False
    )
    op.create_table(
        "document_sections",
        sa.Column("input_file_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["input_file_id"],
            ["input_files.id"],
            name=op.f("fk_document_sections_input_file_id_input_files"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_sections")),
    )
    op.create_index(
        op.f("ix_document_sections_input_file_id_position"),
        "document_sections",
        ["input_file_id", "position"],
        unique=True,
    )
    op.create_table(
        "evaluator_set_versions",
        sa.Column("evaluator_set_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_evaluator_set_versions_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["evaluator_set_id"],
            ["evaluator_sets.id"],
            name=op.f("fk_evaluator_set_versions_evaluator_set_id_evaluator_sets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluator_set_versions")),
    )
    op.create_index(
        op.f("ix_evaluator_set_versions_evaluator_set_id_version"),
        "evaluator_set_versions",
        ["evaluator_set_id", "version"],
        unique=True,
    )
    op.create_table(
        "llm_calls",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("credential_id", sa.Uuid(), nullable=True),
        sa.Column("experiment_id", sa.Uuid(), nullable=True),
        sa.Column("test_case_run_id", sa.Uuid(), nullable=True),
        sa.Column(
            "purpose",
            sa.Enum(
                "test_run",
                "generation",
                "judge",
                "assistant",
                name="call_purpose",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("succeeded", "failed", name="call_status", native_enum=False, create_constraint=True, length=32),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=400), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("request_messages", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column("finish_reason", sa.String(length=64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("ttft_ms", sa.Integer(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("labels", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("trace_id", sa.String(length=32), nullable=False),
        sa.Column("span_id", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["credential_id"],
            ["provider_credentials.id"],
            name=op.f("fk_llm_calls_credential_id_provider_credentials"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_llm_calls_project_id_projects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_calls")),
    )
    op.create_index(op.f("ix_llm_calls_experiment_id"), "llm_calls", ["experiment_id"], unique=False)
    op.create_index(op.f("ix_llm_calls_project_id_id"), "llm_calls", ["project_id", "id"], unique=False)
    op.create_index(op.f("ix_llm_calls_project_id_purpose"), "llm_calls", ["project_id", "purpose"], unique=False)
    op.create_table(
        "model_profiles",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("credential_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=300), nullable=False),
        sa.Column("display_name", sa.String(length=300), nullable=False),
        sa.Column("litellm_model", sa.String(length=400), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("supports_json_mode", sa.Boolean(), nullable=False),
        sa.Column("supports_system_prompt", sa.Boolean(), nullable=False),
        sa.Column("input_price_per_mtok", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("output_price_per_mtok", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column(
            "price_source",
            sa.Enum(
                "override",
                "provider",
                "litellm",
                "free",
                "unknown",
                name="price_source",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("is_selected", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["credential_id"],
            ["provider_credentials.id"],
            name=op.f("fk_model_profiles_credential_id_provider_credentials"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_model_profiles_project_id_projects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_profiles")),
    )
    op.create_index(
        op.f("ix_model_profiles_credential_id_model_name"),
        "model_profiles",
        ["credential_id", "model_name"],
        unique=True,
    )
    op.create_index(
        op.f("ix_model_profiles_project_id_is_selected"), "model_profiles", ["project_id", "is_selected"], unique=False
    )
    op.create_table(
        "prompt_versions",
        sa.Column("prompt_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.Uuid(), nullable=True),
        sa.Column("system_template", sa.Text(), nullable=True),
        sa.Column("user_template", sa.Text(), nullable=True),
        sa.Column("variables", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("default_params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "source",
            sa.Enum("manual", "assistant", name="prompt_source", native_enum=False, create_constraint=True, length=32),
            nullable=False,
        ),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "system_template IS NOT NULL OR user_template IS NOT NULL", name=op.f("ck_prompt_versions_has_template")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_prompt_versions_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["parent_version_id"],
            ["prompt_versions.id"],
            name=op.f("fk_prompt_versions_parent_version_id_prompt_versions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["prompt_id"], ["prompts.id"], name=op.f("fk_prompt_versions_prompt_id_prompts"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prompt_versions")),
    )
    op.create_index(
        op.f("ix_prompt_versions_prompt_id_version"), "prompt_versions", ["prompt_id", "version"], unique=True
    )
    op.create_table(
        "evaluator_configs",
        sa.Column("evaluator_set_version_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("evaluator_name", sa.String(length=100), nullable=False),
        sa.Column("evaluator_version", sa.String(length=32), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("threshold", sa.Double(), nullable=False),
        sa.Column("weight", sa.Double(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["evaluator_set_version_id"],
            ["evaluator_set_versions.id"],
            name=op.f("fk_evaluator_configs_evaluator_set_version_id_evaluator_set_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluator_configs")),
    )
    op.create_index(
        op.f("ix_evaluator_configs_evaluator_set_version_id_position"),
        "evaluator_configs",
        ["evaluator_set_version_id", "position"],
        unique=True,
    )
    op.create_table(
        "optimization_sessions",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("root_prompt_version_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "active", "closed", name="optimization_status", native_enum=False, create_constraint=True, length=32
            ),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_optimization_sessions_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["root_prompt_version_id"],
            ["prompt_versions.id"],
            name=op.f("fk_optimization_sessions_root_prompt_version_id_prompt_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_optimization_sessions")),
    )
    op.create_index(
        op.f("ix_optimization_sessions_project_id_id"), "optimization_sessions", ["project_id", "id"], unique=False
    )
    op.create_table(
        "task_specs",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("prompt_version_id", sa.Uuid(), nullable=False),
        sa.Column("spec", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "confirmed", name="task_spec_status", native_enum=False, create_constraint=True, length=32
            ),
            nullable=False,
        ),
        sa.Column("generator_credential_id", sa.Uuid(), nullable=True),
        sa.Column("generator_model", sa.String(length=300), nullable=True),
        sa.Column("llm_call_id", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["generator_credential_id"],
            ["provider_credentials.id"],
            name=op.f("fk_task_specs_generator_credential_id_provider_credentials"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["llm_call_id"], ["llm_calls.id"], name=op.f("fk_task_specs_llm_call_id_llm_calls"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_task_specs_project_id_projects"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["prompt_version_id"],
            ["prompt_versions.id"],
            name=op.f("fk_task_specs_prompt_version_id_prompt_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_specs")),
    )
    op.create_index(op.f("ix_task_specs_project_id_id"), "task_specs", ["project_id", "id"], unique=False)
    op.create_table(
        "dataset_versions",
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "approved", name="dataset_version_status", native_enum=False, create_constraint=True, length=32
            ),
            nullable=False,
        ),
        sa.Column("task_spec_id", sa.Uuid(), nullable=True),
        sa.Column("holdout_ratio", sa.Double(), nullable=True),
        sa.Column("split_seed", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["approved_by"], ["users.id"], name=op.f("fk_dataset_versions_approved_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], name=op.f("fk_dataset_versions_dataset_id_datasets"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["task_spec_id"],
            ["task_specs.id"],
            name=op.f("fk_dataset_versions_task_spec_id_task_specs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_versions")),
    )
    op.create_index(
        op.f("ix_dataset_versions_dataset_id_version"), "dataset_versions", ["dataset_id", "version"], unique=True
    )
    op.create_table(
        "dataset_items",
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expected_output", sa.Text(), nullable=True),
        sa.Column("rubric", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "golden",
                "input_file",
                "generated",
                name="item_source",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "review_status",
            sa.Enum(
                "trusted",
                "draft",
                "approved",
                name="review_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "split",
            sa.Enum("optimize", "holdout", name="split", native_enum=False, create_constraint=True, length=32),
            nullable=True,
        ),
        sa.Column("input_file_id", sa.Uuid(), nullable=True),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_dataset_items_dataset_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["input_file_id"],
            ["input_files.id"],
            name=op.f("fk_dataset_items_input_file_id_input_files"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_items")),
    )
    op.create_index(
        op.f("ix_dataset_items_dataset_version_id_category"),
        "dataset_items",
        ["dataset_version_id", "category"],
        unique=False,
    )
    op.create_index(
        op.f("ix_dataset_items_dataset_version_id_id"), "dataset_items", ["dataset_version_id", "id"], unique=False
    )
    op.create_index(
        op.f("ix_dataset_items_dataset_version_id_split"),
        "dataset_items",
        ["dataset_version_id", "split"],
        unique=False,
    )
    op.create_table(
        "experiments",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "planned",
                "running",
                "paused",
                "evaluating",
                "completed",
                "cancelled",
                "failed",
                name="experiment_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "origin",
            sa.Enum(
                "manual", "optimization", name="experiment_origin", native_enum=False, create_constraint=True, length=32
            ),
            nullable=False,
        ),
        sa.Column("prompt_version_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("evaluator_set_version_id", sa.Uuid(), nullable=False),
        sa.Column(
            "split_scope",
            sa.Enum(
                "all", "optimize", "holdout", name="split_scope", native_enum=False, create_constraint=True, length=32
            ),
            nullable=False,
        ),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("estimate", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("budget_cap", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("total_calls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_experiments_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_experiments_dataset_version_id_dataset_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evaluator_set_version_id"],
            ["evaluator_set_versions.id"],
            name=op.f("fk_experiments_evaluator_set_version_id_evaluator_set_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_experiments_project_id_projects"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["prompt_version_id"],
            ["prompt_versions.id"],
            name=op.f("fk_experiments_prompt_version_id_prompt_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_experiments")),
    )
    op.create_index(op.f("ix_experiments_project_id_id"), "experiments", ["project_id", "id"], unique=False)
    op.create_index(op.f("ix_experiments_status"), "experiments", ["status"], unique=False)
    op.create_table(
        "evaluation_runs",
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("evaluator_set_version_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "completed",
                "failed",
                name="evaluation_run_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "trigger",
            sa.Enum(
                "initial", "rescore", name="evaluation_trigger", native_enum=False, create_constraint=True, length=32
            ),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["evaluator_set_version_id"],
            ["evaluator_set_versions.id"],
            name=op.f("fk_evaluation_runs_evaluator_set_version_id_evaluator_set_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.id"],
            name=op.f("fk_evaluation_runs_experiment_id_experiments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_runs")),
    )
    op.create_index(
        op.f("ix_evaluation_runs_experiment_id_id"), "evaluation_runs", ["experiment_id", "id"], unique=False
    )
    op.create_table(
        "experiment_events",
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column(
            "from_status",
            sa.Enum(
                "draft",
                "planned",
                "running",
                "paused",
                "evaluating",
                "completed",
                "cancelled",
                "failed",
                name="experiment_event_from",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column(
            "to_status",
            sa.Enum(
                "draft",
                "planned",
                "running",
                "paused",
                "evaluating",
                "completed",
                "cancelled",
                "failed",
                name="experiment_event_to",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.id"],
            name=op.f("fk_experiment_events_experiment_id_experiments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_experiment_events")),
    )
    op.create_index(
        op.f("ix_experiment_events_experiment_id_id"), "experiment_events", ["experiment_id", "id"], unique=False
    )
    op.create_table(
        "prompt_candidates",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("base_prompt_version_id", sa.Uuid(), nullable=False),
        sa.Column("prompt_version_id", sa.Uuid(), nullable=False),
        sa.Column("strategy", sa.String(length=64), nullable=False),
        sa.Column("target_cluster_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("diff", sa.Text(), nullable=False),
        sa.Column("change_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("optimize_experiment_id", sa.Uuid(), nullable=True),
        sa.Column("holdout_experiment_id", sa.Uuid(), nullable=True),
        sa.Column(
            "outcome",
            sa.Enum(
                "pending",
                "better",
                "not_better",
                "accepted",
                "rejected",
                name="candidate_outcome",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["base_prompt_version_id"],
            ["prompt_versions.id"],
            name=op.f("fk_prompt_candidates_base_prompt_version_id_prompt_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["holdout_experiment_id"],
            ["experiments.id"],
            name=op.f("fk_prompt_candidates_holdout_experiment_id_experiments"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["optimize_experiment_id"],
            ["experiments.id"],
            name=op.f("fk_prompt_candidates_optimize_experiment_id_experiments"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["prompt_version_id"],
            ["prompt_versions.id"],
            name=op.f("fk_prompt_candidates_prompt_version_id_prompt_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["optimization_sessions.id"],
            name=op.f("fk_prompt_candidates_session_id_optimization_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prompt_candidates")),
    )
    op.create_index(op.f("ix_prompt_candidates_session_id_id"), "prompt_candidates", ["session_id", "id"], unique=False)
    op.create_table(
        "test_case_runs",
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_item_id", sa.Uuid(), nullable=False),
        sa.Column("prompt_version_id", sa.Uuid(), nullable=False),
        sa.Column("model_profile_id", sa.Uuid(), nullable=False),
        sa.Column("credential_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=400), nullable=False),
        sa.Column("param_set_key", sa.String(length=64), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("run_number", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "succeeded",
                "failed",
                "skipped",
                name="run_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("rendered_system_prompt", sa.Text(), nullable=True),
        sa.Column("rendered_user_prompt", sa.Text(), nullable=True),
        sa.Column("raw_output", sa.Text(), nullable=True),
        sa.Column("parsed_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("finish_reason", sa.String(length=64), nullable=True),
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("ttft_ms", sa.Integer(), nullable=True),
        sa.Column("llm_call_id", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("span_id", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_item_id"],
            ["dataset_items.id"],
            name=op.f("fk_test_case_runs_dataset_item_id_dataset_items"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.id"],
            name=op.f("fk_test_case_runs_experiment_id_experiments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["prompt_version_id"],
            ["prompt_versions.id"],
            name=op.f("fk_test_case_runs_prompt_version_id_prompt_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("experiment_id", "id", name=op.f("pk_test_case_runs")),
    )
    op.create_index(
        op.f("ix_test_case_runs_experiment_id_dataset_item_id"),
        "test_case_runs",
        ["experiment_id", "dataset_item_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_test_case_runs_experiment_id_model_profile_id_param_set_key"),
        "test_case_runs",
        ["experiment_id", "model_profile_id", "param_set_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_test_case_runs_experiment_id_status"), "test_case_runs", ["experiment_id", "status"], unique=False
    )
    op.create_table(
        "failure_clusters",
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_run_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("rule_tag", sa.String(length=64), nullable=True),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("affected_models", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("categories", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("example_case_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("llm_call_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["evaluation_run_id"],
            ["evaluation_runs.id"],
            name=op.f("fk_failure_clusters_evaluation_run_id_evaluation_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.id"],
            name=op.f("fk_failure_clusters_experiment_id_experiments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["llm_call_id"],
            ["llm_calls.id"],
            name=op.f("fk_failure_clusters_llm_call_id_llm_calls"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_failure_clusters")),
    )
    op.create_index(
        op.f("ix_failure_clusters_evaluation_run_id_id"), "failure_clusters", ["evaluation_run_id", "id"], unique=False
    )
    op.create_table(
        "prompt_reviews",
        sa.Column("prompt_version_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_run_id", sa.Uuid(), nullable=True),
        sa.Column("checks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["evaluation_run_id"],
            ["evaluation_runs.id"],
            name=op.f("fk_prompt_reviews_evaluation_run_id_evaluation_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["prompt_version_id"],
            ["prompt_versions.id"],
            name=op.f("fk_prompt_reviews_prompt_version_id_prompt_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prompt_reviews")),
    )
    op.create_index(
        op.f("ix_prompt_reviews_prompt_version_id_id"), "prompt_reviews", ["prompt_version_id", "id"], unique=False
    )
    op.create_table(
        "scores",
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_run_id", sa.Uuid(), nullable=False),
        sa.Column("test_case_run_id", sa.Uuid(), nullable=False),
        sa.Column("evaluator_name", sa.String(length=100), nullable=False),
        sa.Column("evaluator_version", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Double(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("weight", sa.Double(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("llm_call_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["evaluation_run_id"],
            ["evaluation_runs.id"],
            name=op.f("fk_scores_evaluation_run_id_evaluation_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id", "test_case_run_id"],
            ["test_case_runs.experiment_id", "test_case_runs.id"],
            name=op.f("fk_scores_experiment_id_test_case_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["experiment_id"], ["experiments.id"], name=op.f("fk_scores_experiment_id_experiments"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("experiment_id", "id", name=op.f("pk_scores")),
    )
    op.create_index(
        op.f("ix_scores_evaluation_run_id_test_case_run_id_evaluator_name"),
        "scores",
        ["evaluation_run_id", "test_case_run_id", "evaluator_name"],
        unique=True,
    )
    op.create_index(
        op.f("ix_scores_experiment_id_evaluation_run_id"),
        "scores",
        ["experiment_id", "evaluation_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_scores_experiment_id_evaluation_run_id"), table_name="scores")
    op.drop_index(op.f("ix_scores_evaluation_run_id_test_case_run_id_evaluator_name"), table_name="scores")
    op.drop_table("scores")
    op.drop_index(op.f("ix_prompt_reviews_prompt_version_id_id"), table_name="prompt_reviews")
    op.drop_table("prompt_reviews")
    op.drop_index(op.f("ix_failure_clusters_evaluation_run_id_id"), table_name="failure_clusters")
    op.drop_table("failure_clusters")
    op.drop_index(op.f("ix_test_case_runs_experiment_id_status"), table_name="test_case_runs")
    op.drop_index(op.f("ix_test_case_runs_experiment_id_model_profile_id_param_set_key"), table_name="test_case_runs")
    op.drop_index(op.f("ix_test_case_runs_experiment_id_dataset_item_id"), table_name="test_case_runs")
    op.drop_table("test_case_runs")
    op.drop_index(op.f("ix_prompt_candidates_session_id_id"), table_name="prompt_candidates")
    op.drop_table("prompt_candidates")
    op.drop_index(op.f("ix_experiment_events_experiment_id_id"), table_name="experiment_events")
    op.drop_table("experiment_events")
    op.drop_index(op.f("ix_evaluation_runs_experiment_id_id"), table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_index(op.f("ix_experiments_status"), table_name="experiments")
    op.drop_index(op.f("ix_experiments_project_id_id"), table_name="experiments")
    op.drop_table("experiments")
    op.drop_index(op.f("ix_dataset_items_dataset_version_id_split"), table_name="dataset_items")
    op.drop_index(op.f("ix_dataset_items_dataset_version_id_id"), table_name="dataset_items")
    op.drop_index(op.f("ix_dataset_items_dataset_version_id_category"), table_name="dataset_items")
    op.drop_table("dataset_items")
    op.drop_index(op.f("ix_dataset_versions_dataset_id_version"), table_name="dataset_versions")
    op.drop_table("dataset_versions")
    op.drop_index(op.f("ix_task_specs_project_id_id"), table_name="task_specs")
    op.drop_table("task_specs")
    op.drop_index(op.f("ix_optimization_sessions_project_id_id"), table_name="optimization_sessions")
    op.drop_table("optimization_sessions")
    op.drop_index(op.f("ix_evaluator_configs_evaluator_set_version_id_position"), table_name="evaluator_configs")
    op.drop_table("evaluator_configs")
    op.drop_index(op.f("ix_prompt_versions_prompt_id_version"), table_name="prompt_versions")
    op.drop_table("prompt_versions")
    op.drop_index(op.f("ix_model_profiles_project_id_is_selected"), table_name="model_profiles")
    op.drop_index(op.f("ix_model_profiles_credential_id_model_name"), table_name="model_profiles")
    op.drop_table("model_profiles")
    op.drop_index(op.f("ix_llm_calls_project_id_purpose"), table_name="llm_calls")
    op.drop_index(op.f("ix_llm_calls_project_id_id"), table_name="llm_calls")
    op.drop_index(op.f("ix_llm_calls_experiment_id"), table_name="llm_calls")
    op.drop_table("llm_calls")
    op.drop_index(op.f("ix_evaluator_set_versions_evaluator_set_id_version"), table_name="evaluator_set_versions")
    op.drop_table("evaluator_set_versions")
    op.drop_index(op.f("ix_document_sections_input_file_id_position"), table_name="document_sections")
    op.drop_table("document_sections")
    op.drop_index(op.f("ix_provider_credentials_project_id_id"), table_name="provider_credentials")
    op.drop_table("provider_credentials")
    op.drop_index(op.f("ix_prompts_project_id_id"), table_name="prompts")
    op.drop_table("prompts")
    op.drop_index(op.f("ix_input_files_project_id_id"), table_name="input_files")
    op.drop_table("input_files")
    op.drop_index(op.f("ix_evaluator_sets_project_id_id"), table_name="evaluator_sets")
    op.drop_table("evaluator_sets")
    op.drop_index(op.f("ix_datasets_project_id_id"), table_name="datasets")
    op.drop_table("datasets")
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_family_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index(op.f("ix_projects_organization_id_id"), table_name="projects")
    op.drop_table("projects")
    op.drop_index(op.f("ix_memberships_user_id"), table_name="memberships")
    op.drop_index(op.f("ix_memberships_organization_id_user_id"), table_name="memberships")
    op.drop_table("memberships")
    op.drop_table("users")
    op.drop_table("organizations")
