/** Members and invites: who is in the workspace with which role, and invite links (copy, issue again, withdraw). */
"use client"

import { useState } from "react"
import { toast } from "sonner"

import { CopyButton } from "@/components/common/copy-button"
import { ErrorMessage } from "@/components/common/error-message"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { NativeSelect } from "@/components/ui/select"
import type { InviteIssued, MembershipRole } from "@/lib/api/types"

import { dateTime, grantableRoles, ROLE_TEXT } from "../domain"
import {
  useChangeRole,
  useCreateInvite,
  useInvites,
  useMembers,
  useReissueInvite,
  useRemoveMember,
  useRevokeInvite,
} from "../hooks"

type Props = { organizationId: string; role: MembershipRole; personal: boolean; selfId: string | undefined }

export function MembersPanel({ organizationId, role, personal, selfId }: Props) {
  const manage = grantableRoles(role).length > 0
  const members = useMembers(organizationId)
  const invites = useInvites(organizationId, manage)
  const change = useChangeRole(organizationId)
  const remove = useRemoveMember(organizationId)
  const create = useCreateInvite(organizationId)
  const reissue = useReissueInvite(organizationId)
  const revoke = useRevokeInvite(organizationId)
  const [issued, setIssued] = useState<InviteIssued | null>(null)
  const [email, setEmail] = useState("")
  const [inviteRole, setInviteRole] = useState<MembershipRole>("member")
  const grantable = grantableRoles(role)
  const error = members.error ?? change.error ?? remove.error ?? create.error ?? reissue.error ?? revoke.error

  async function invite() {
    const result = await create.mutateAsync({ email, role: inviteRole })
    setIssued(result)
    setEmail("")
    toast.success(result.emailed ? "Invite sent by email." : "Invite made. Copy the link and send it.")
  }

  return (
    <div className="flex flex-col gap-6">
      <ErrorMessage error={error} />
      <ul className="border-border divide-border divide-y rounded-xl border">
        {(members.data ?? []).map((m) => (
          <li key={m.user_id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
            <span className="flex flex-col">
              <span className="text-sm font-medium">
                {m.name} {m.user_id === selfId ? <span className="text-text-muted">(you)</span> : null}
              </span>
              <span className="text-text-secondary text-xs">
                {m.email} {m.email_verified ? "" : "(email not confirmed)"} · joined {dateTime(m.joined_at)}
              </span>
            </span>
            <span className="flex items-center gap-2">
              {manage && m.user_id !== selfId ? (
                <>
                  <NativeSelect
                    aria-label={`Role of ${m.name}`}
                    value={m.role}
                    onChange={(e) =>
                      change.mutate({ userId: m.user_id, role: e.target.value as MembershipRole })
                    }
                    className="h-8 w-28"
                  >
                    {[...new Set([m.role, ...grantable])].map((r) => (
                      <option key={r} value={r}>
                        {ROLE_TEXT[r].label}
                      </option>
                    ))}
                  </NativeSelect>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={personal}
                    onClick={() => {
                      if (window.confirm(`Remove ${m.name} from this workspace?`)) remove.mutate(m.user_id)
                    }}
                  >
                    Remove
                  </Button>
                </>
              ) : (
                <Badge variant="secondary">{ROLE_TEXT[m.role].label}</Badge>
              )}
            </span>
          </li>
        ))}
      </ul>

      <dl className="text-text-secondary grid gap-1 text-xs sm:grid-cols-2">
        {Object.entries(ROLE_TEXT).map(([r, t]) => (
          <div key={r}>
            <dt className="text-foreground inline font-medium">{t.label}: </dt>
            <dd className="inline">{t.what}</dd>
          </div>
        ))}
      </dl>

      {manage ? (
        <section className="flex flex-col gap-3">
          <h3 className="text-base font-semibold">Invite someone</h3>
          {personal ? (
            <p className="text-text-secondary text-sm">
              This is a personal workspace. Invites are for shared workspaces.
            </p>
          ) : (
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                void invite().catch(() => undefined)
              }}
            >
              <Input
                type="email"
                required
                aria-label="Email address"
                placeholder="name@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-72"
              />
              <NativeSelect
                aria-label="Role"
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as MembershipRole)}
                className="h-9 w-32"
              >
                {grantable.map((r) => (
                  <option key={r} value={r}>
                    {ROLE_TEXT[r].label}
                  </option>
                ))}
              </NativeSelect>
              <Button type="submit" disabled={create.isPending}>
                Send invite
              </Button>
            </form>
          )}
          {issued ? (
            <div className="bg-muted flex flex-wrap items-center gap-2 rounded-lg p-3 text-sm">
              <span>
                Link for {issued.email} (shown once, works until {dateTime(issued.expires_at)}):
              </span>
              <code className="max-w-full truncate text-xs">{issued.link}</code>
              <CopyButton text={issued.link} />
            </div>
          ) : null}
          <ul className="flex flex-col gap-2">
            {(invites.data ?? []).map((i) => (
              <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                <span>
                  {i.email} as {ROLE_TEXT[i.role].label} <Badge variant="outline">{i.status}</Badge>{" "}
                  <span className="text-text-muted text-xs">expires {dateTime(i.expires_at)}</span>
                </span>
                <span className="flex gap-1">
                  {i.status !== "accepted" ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void reissue.mutateAsync(i.id).then(setIssued, () => undefined)}
                    >
                      Send a new link
                    </Button>
                  ) : null}
                  {i.status === "open" ? (
                    <Button size="sm" variant="ghost" onClick={() => revoke.mutate(i.id)}>
                      Withdraw
                    </Button>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}
