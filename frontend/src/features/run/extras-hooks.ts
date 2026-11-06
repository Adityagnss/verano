/** Hooks for the Run step's extras: what each model accepts, and the "update checks" preview and apply. */
"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"

export function useRunOptions(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "run-options"],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/experiments/run-options", {
          params: { path: { project_id: projectId } },
        }),
      ),
  })
}

export function useDefaultsPreview(projectId: string, versionId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ["projects", projectId, "default-update", versionId],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/evaluator-set-versions/{version_id}/default-update", {
          params: { path: { project_id: projectId, version_id: versionId! } },
        }),
      ),
    enabled: enabled && versionId !== null,
    retry: false,
  })
}

export function useApplyDefaults(projectId: string, versionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { skip: string[]; remove: string[] }) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/evaluator-set-versions/{version_id}/default-update", {
          params: { path: { project_id: projectId, version_id: versionId } },
          body,
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["projects", projectId] }),
  })
}
