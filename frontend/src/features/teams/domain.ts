/**
 * Roles as the screens use them. The server is the only authority (it refuses what a role may not do);
 * these helpers only decide what to show, so a viewer is not offered buttons that would be refused.
 */
import type { MembershipRole } from "@/lib/api/types"

const RANK: Record<MembershipRole, number> = { viewer: 0, member: 1, admin: 2, owner: 3 }

export const ROLES: MembershipRole[] = ["viewer", "member", "admin", "owner"]

export const ROLE_TEXT: Record<MembershipRole, { label: string; what: string }> = {
  owner: { label: "Owner", what: "Everything, including making other owners." },
  admin: { label: "Admin", what: "Manages people, keys, the spending limit and the audit log." },
  member: { label: "Member", what: "Works in projects: edits, runs tests, labels answers." },
  viewer: { label: "Viewer", what: "Reads results. Can't start runs, change keys or delete." },
}

export function atLeast(role: MembershipRole | undefined, minimum: MembershipRole): boolean {
  return role !== undefined && RANK[role] >= RANK[minimum]
}

/** The roles this role may give to someone else: owners any, admins only member and viewer. */
export function grantableRoles(role: MembershipRole | undefined): MembershipRole[] {
  if (role === "owner") return ROLES
  if (role === "admin") return ROLES.filter((r) => RANK[r] <= RANK.member)
  return []
}

export function money(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "-"
  return Number(value).toLocaleString(undefined, { style: "currency", currency: "USD" })
}

export function dateTime(value: string): string {
  return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
}
