/**
 * Prompt label hooks: the labels on a prompt, their history, and the changes (set, roll back,
 * remove, and the "move on accept" choice). Every change refreshes the label queries.
 */
"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"

const HISTORY_SIZE = 20

const keys = {
  labels: (projectId: string, promptId: string) => ["projects", projectId, "labels", promptId] as const,
  history: (projectId: string, promptId: string) =>
    ["projects", projectId, "label-history", promptId] as const,
}

function path(projectId: string, promptId: string) {
  return { project_id: projectId, prompt_id: promptId }
}

export function useLabels(projectId: string, promptId: string) {
  return useQuery({
    queryKey: keys.labels(projectId, promptId),
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/prompts/{prompt_id}/labels", {
          params: { path: path(projectId, promptId) },
        }),
      ),
  })
}

export function useLabelHistory(projectId: string, promptId: string) {
  return useQuery({
    queryKey: keys.history(projectId, promptId),
    queryFn: async () => {
      const page = await call(() =>
        api.GET("/api/v1/projects/{project_id}/prompts/{prompt_id}/label-history", {
          params: { path: path(projectId, promptId), query: { limit: HISTORY_SIZE } },
        }),
      )
      return page.items
    },
  })
}

function useRefresh(projectId: string, promptId: string) {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: keys.labels(projectId, promptId) }),
      queryClient.invalidateQueries({ queryKey: keys.history(projectId, promptId) }),
    ])
}

export function useSetLabel(projectId: string, promptId: string) {
  const refresh = useRefresh(projectId, promptId)
  return useMutation({
    mutationFn: (input: { name: string; versionId: string }) =>
      call(() =>
        api.PUT("/api/v1/projects/{project_id}/prompts/{prompt_id}/labels/{name}", {
          params: { path: { ...path(projectId, promptId), name: input.name } },
          body: { version_id: input.versionId },
        }),
      ),
    onSuccess: refresh,
  })
}

export function useRollBackLabel(projectId: string, promptId: string) {
  const refresh = useRefresh(projectId, promptId)
  return useMutation({
    mutationFn: (name: string) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/prompts/{prompt_id}/labels/{name}/rollback", {
          params: { path: { ...path(projectId, promptId), name } },
        }),
      ),
    onSuccess: refresh,
  })
}

export function useRemoveLabel(projectId: string, promptId: string) {
  const refresh = useRefresh(projectId, promptId)
  return useMutation({
    mutationFn: (name: string) =>
      call(() =>
        api.DELETE("/api/v1/projects/{project_id}/prompts/{prompt_id}/labels/{name}", {
          params: { path: { ...path(projectId, promptId), name } },
        }),
      ),
    onSuccess: refresh,
  })
}

export function useAcceptMovesLabel(projectId: string, promptId: string) {
  const refresh = useRefresh(projectId, promptId)
  return useMutation({
    mutationFn: (name: string | null) =>
      call(() =>
        api.PUT("/api/v1/projects/{project_id}/prompts/{prompt_id}/label-settings", {
          params: { path: path(projectId, promptId) },
          body: { accept_moves_label: name },
        }),
      ),
    onSuccess: refresh,
  })
}
