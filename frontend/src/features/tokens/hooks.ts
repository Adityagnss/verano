/** API token hooks: list, create (the secret is returned once) and revoke. */
"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"

const KEY = ["api-tokens"] as const

export function useTokens() {
  return useQuery({ queryKey: KEY, queryFn: () => call(() => api.GET("/api/v1/auth/tokens")) })
}

export function useTokenProjects() {
  return useQuery({
    queryKey: ["api-token-projects"],
    queryFn: async () => {
      const page = await call(() => api.GET("/api/v1/projects", { params: { query: { limit: 100 } } }))
      return page.items
    },
  })
}

export function useCreateToken() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: {
      name: string
      scope: "full" | "read"
      projectId: string | null
      days: number | null
    }) =>
      call(() =>
        api.POST("/api/v1/auth/tokens", {
          body: {
            name: input.name,
            scope: input.scope,
            project_id: input.projectId,
            expires_in_days: input.days,
          },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  })
}

export function useRevokeToken() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      call(() => api.DELETE("/api/v1/auth/tokens/{token_id}", { params: { path: { token_id: id } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  })
}
