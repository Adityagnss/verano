/**
 * Keys step hooks: providers, the project's credentials and discovered models, and the
 * mutations that change them. Models are loaded page by page until the cursor runs out, so
 * providers that expose hundreds of models are shown in full.
 */
"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"
import type { CredentialCreate, ModelProfileOut } from "@/lib/api/types"

const PAGE_SIZE = 200

const keys = {
  providers: ["providers"] as const,
  credentials: (projectId: string) => ["projects", projectId, "credentials"] as const,
  models: (projectId: string) => ["projects", projectId, "models"] as const,
}

function path(projectId: string) {
  return { path: { project_id: projectId } }
}

export function useProviders() {
  return useQuery({ queryKey: keys.providers, queryFn: () => call(() => api.GET("/api/v1/providers")) })
}

export function useCredentials(projectId: string) {
  return useQuery({
    queryKey: keys.credentials(projectId),
    queryFn: () =>
      call(() => api.GET("/api/v1/projects/{project_id}/credentials", { params: path(projectId) })),
  })
}

async function allModels(projectId: string): Promise<ModelProfileOut[]> {
  const models: ModelProfileOut[] = []
  let cursor: string | undefined
  do {
    const page = await call(() =>
      api.GET("/api/v1/projects/{project_id}/models", {
        params: { ...path(projectId), query: { limit: PAGE_SIZE, cursor } },
      }),
    )
    models.push(...page.items)
    cursor = page.next_cursor ?? undefined
  } while (cursor)
  return models
}

export function useModels(projectId: string) {
  return useQuery({ queryKey: keys.models(projectId), queryFn: () => allModels(projectId) })
}

function useInvalidateProject(projectId: string) {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ["projects", projectId] })
}

export function useAddCredential(projectId: string) {
  const invalidate = useInvalidateProject(projectId)
  return useMutation({
    mutationFn: (body: CredentialCreate) =>
      call(() => api.POST("/api/v1/projects/{project_id}/credentials", { params: path(projectId), body })),
    onSuccess: invalidate,
  })
}

export function useRefreshModels(projectId: string) {
  const invalidate = useInvalidateProject(projectId)
  return useMutation({
    mutationFn: (credentialId: string) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/credentials/{credential_id}/discover", {
          params: { path: { project_id: projectId, credential_id: credentialId } },
        }),
      ),
    onSettled: invalidate,
  })
}

export function useRemoveCredential(projectId: string) {
  const invalidate = useInvalidateProject(projectId)
  return useMutation({
    mutationFn: (credentialId: string) =>
      call(() =>
        api.DELETE("/api/v1/projects/{project_id}/credentials/{credential_id}", {
          params: { path: { project_id: projectId, credential_id: credentialId } },
        }),
      ),
    onSuccess: invalidate,
  })
}

export function useSaveSelection(projectId: string) {
  const invalidate = useInvalidateProject(projectId)
  return useMutation({
    mutationFn: (body: { selected: string[]; unselected: string[] }) =>
      call(() =>
        api.PUT("/api/v1/projects/{project_id}/models/selection", { params: path(projectId), body }),
      ),
    onSuccess: invalidate,
  })
}

/** Keys already added in this organization's other projects (so a key is typed once). */
export function useSharedKeys(projectId: string) {
  return useQuery({
    queryKey: [...keys.credentials(projectId), "in-other-projects"],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/credentials/in-other-projects", { params: path(projectId) }),
      ),
  })
}

export function useCopyKey(projectId: string) {
  const invalidate = useInvalidateProject(projectId)
  return useMutation({
    mutationFn: (credentialId: string) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/credentials/copy", {
          params: path(projectId),
          body: { credential_id: credentialId },
        }),
      ),
    onSuccess: invalidate,
  })
}
