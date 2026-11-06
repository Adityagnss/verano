/**
 * Teams hooks: the signed-in user's workspaces and roles, members and invites, the workspace key store,
 * the audit log (with download) and the spending limit. Everything is keyed by workspace id.
 */
"use client"

import {
  type InfiniteData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query"

import { api, ApiError, call } from "@/lib/api/client"
import type { AuditPage, MembershipRole, OrgKeyCreate } from "@/lib/api/types"
import { accessToken } from "@/lib/auth/session"

function org(organizationId: string) {
  return { path: { organization_id: organizationId } }
}

const k = {
  me: ["me"] as const,
  members: (o: string) => ["organizations", o, "members"] as const,
  invites: (o: string) => ["organizations", o, "invites"] as const,
  keys: (o: string) => ["organizations", o, "keys"] as const,
  limit: (o: string) => ["organizations", o, "guardrails"] as const,
  audit: (o: string, filters: AuditFilters) => ["organizations", o, "audit", filters] as const,
  actions: (o: string) => ["organizations", o, "audit-actions"] as const,
}

export function useMe() {
  return useQuery({ queryKey: k.me, queryFn: () => call(() => api.GET("/api/v1/auth/me")) })
}

export function useMembers(organizationId: string) {
  return useQuery({
    queryKey: k.members(organizationId),
    queryFn: () =>
      call(() => api.GET("/api/v1/organizations/{organization_id}/members", { params: org(organizationId) })),
  })
}

export function useChangeRole(organizationId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (v: { userId: string; role: MembershipRole }) =>
      call(() =>
        api.PATCH("/api/v1/organizations/{organization_id}/members/{user_id}", {
          params: { path: { organization_id: organizationId, user_id: v.userId } },
          body: { role: v.role },
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["organizations", organizationId] }),
  })
}

export function useRemoveMember(organizationId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) =>
      call(() =>
        api.DELETE("/api/v1/organizations/{organization_id}/members/{user_id}", {
          params: { path: { organization_id: organizationId, user_id: userId } },
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["organizations", organizationId] }),
  })
}

export function useInvites(organizationId: string, enabled: boolean) {
  return useQuery({
    queryKey: k.invites(organizationId),
    enabled,
    queryFn: () =>
      call(() => api.GET("/api/v1/organizations/{organization_id}/invites", { params: org(organizationId) })),
  })
}

export function useCreateInvite(organizationId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { email: string; role: MembershipRole }) =>
      call(() =>
        api.POST("/api/v1/organizations/{organization_id}/invites", { params: org(organizationId), body }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: k.invites(organizationId) }),
  })
}

export function useReissueInvite(organizationId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (inviteId: string) =>
      call(() =>
        api.POST("/api/v1/organizations/{organization_id}/invites/{invite_id}/reissue", {
          params: { path: { organization_id: organizationId, invite_id: inviteId } },
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: k.invites(organizationId) }),
  })
}

export function useRevokeInvite(organizationId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (inviteId: string) =>
      call(() =>
        api.DELETE("/api/v1/organizations/{organization_id}/invites/{invite_id}", {
          params: { path: { organization_id: organizationId, invite_id: inviteId } },
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: k.invites(organizationId) }),
  })
}

export function useOrgKeys(organizationId: string, enabled: boolean) {
  return useQuery({
    queryKey: k.keys(organizationId),
    enabled,
    queryFn: () =>
      call(() => api.GET("/api/v1/organizations/{organization_id}/keys", { params: org(organizationId) })),
  })
}

export function useCreateOrgKey(organizationId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: OrgKeyCreate) =>
      call(() =>
        api.POST("/api/v1/organizations/{organization_id}/keys", { params: org(organizationId), body }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: k.keys(organizationId) }),
  })
}

export function useRotateOrgKey(organizationId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (v: { keyId: string; apiKey: string }) =>
      call(() =>
        api.POST("/api/v1/organizations/{organization_id}/keys/{key_id}/rotate", {
          params: { path: { organization_id: organizationId, key_id: v.keyId } },
          body: { api_key: v.apiKey },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["organizations", organizationId] }),
  })
}

export function useDeleteOrgKey(organizationId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (keyId: string) =>
      call(() =>
        api.DELETE("/api/v1/organizations/{organization_id}/keys/{key_id}", {
          params: { path: { organization_id: organizationId, key_id: keyId } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: k.keys(organizationId) }),
  })
}

export function useUseKeyInProject(organizationId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (v: { keyId: string; projectId: string }) =>
      call(() =>
        api.POST("/api/v1/organizations/{organization_id}/keys/{key_id}/projects", {
          params: { path: { organization_id: organizationId, key_id: v.keyId } },
          body: { project_id: v.projectId },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["organizations", organizationId] }),
  })
}

export function useStopUsingKey(organizationId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (v: { keyId: string; projectId: string }) =>
      call(() =>
        api.DELETE("/api/v1/organizations/{organization_id}/keys/{key_id}/projects/{project_id}", {
          params: { path: { organization_id: organizationId, key_id: v.keyId, project_id: v.projectId } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["organizations", organizationId] }),
  })
}

export function useGuardrails(organizationId: string) {
  return useQuery({
    queryKey: k.limit(organizationId),
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/organizations/{organization_id}/guardrails", { params: org(organizationId) }),
      ),
  })
}

export function useSetLimit(organizationId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (limit: number | null) =>
      call(() =>
        api.PUT("/api/v1/organizations/{organization_id}/guardrails", {
          params: org(organizationId),
          body: { monthly_spend_limit: limit },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["organizations", organizationId] }),
  })
}

export type AuditFilters = { action?: string; actor_id?: string; since?: string; until?: string }
const PAGE = 50

export function useAuditLog(organizationId: string, filters: AuditFilters) {
  return useInfiniteQuery<
    AuditPage,
    Error,
    InfiniteData<AuditPage>,
    ReturnType<typeof k.audit>,
    string | undefined
  >({
    queryKey: k.audit(organizationId, filters),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    queryFn: ({ pageParam }): Promise<AuditPage> =>
      call(() =>
        api.GET("/api/v1/organizations/{organization_id}/audit-log", {
          params: { ...org(organizationId), query: { filters, limit: PAGE, cursor: pageParam } },
        }),
      ),
  })
}

export function useAuditActions(organizationId: string) {
  return useQuery({
    queryKey: k.actions(organizationId),
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/organizations/{organization_id}/audit-log/actions", { params: org(organizationId) }),
      ),
  })
}

/** Downloads the filtered audit log as a file (the request carries the sign-in, so it can't be a plain link). */
export async function downloadAuditLog(
  organizationId: string,
  format: "csv" | "json",
  filters: AuditFilters,
) {
  const query = new URLSearchParams({ format })
  for (const [name, value] of Object.entries(filters)) if (value) query.set(name, value)
  const response = await fetch(`/api/v1/organizations/${organizationId}/audit-log/export?${query}`, {
    headers: { Authorization: `Bearer ${accessToken() ?? ""}` },
  })
  if (!response.ok)
    throw new ApiError(
      response.status,
      "export_failed",
      "The audit log could not be downloaded. Try again.",
      null,
    )
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement("a")
  link.href = url
  link.download = `audit-log.${format}`
  link.click()
  URL.revokeObjectURL(url)
}

export function useInvitePreview(token: string) {
  return useQuery({
    queryKey: ["invite", token],
    retry: false,
    queryFn: () => call(() => api.GET("/api/v1/auth/invites/{token}", { params: { path: { token } } })),
  })
}

export function useAcceptInvite() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (token: string) =>
      call(() => api.POST("/api/v1/auth/invites/{token}/accept", { params: { path: { token } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: k.me }),
  })
}

export function useVerifyEmail() {
  return useMutation({
    mutationFn: (token: string) => call(() => api.POST("/api/v1/auth/verify-email", { body: { token } })),
  })
}

export function useResendVerification() {
  return useMutation({ mutationFn: () => call(() => api.POST("/api/v1/auth/resend-verification")) })
}

/** Asks the server where to send the browser to sign in with a provider. */
export async function startProviderSignIn(provider: string): Promise<string> {
  const started = await call(() =>
    api.GET("/api/v1/auth/oidc/{provider}/start", { params: { path: { provider } } }),
  )
  return started.authorization_url
}
