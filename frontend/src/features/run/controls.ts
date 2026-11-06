/** Run controls: pause a run, resume it (optionally with a higher budget cap), and retry calls that failed for a passing reason. */
"use client"

import { useMutation, useQueryClient } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"

type Ids = { projectId: string; experimentId: string }

function params({ projectId, experimentId }: Ids) {
  return { path: { project_id: projectId, experiment_id: experimentId } }
}

function useRefresh(projectId: string) {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ["projects", projectId] })
}

export function usePauseRun(projectId: string) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (experimentId: string) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/experiments/{experiment_id}/pause", {
          params: params({ projectId, experimentId }),
        }),
      ),
    onSettled: refresh,
  })
}

export function useResumeRun(projectId: string) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: ({ experimentId, budgetCap }: { experimentId: string; budgetCap: string | null }) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/experiments/{experiment_id}/resume", {
          params: params({ projectId, experimentId }),
          body: { budget_cap: budgetCap },
        }),
      ),
    onSettled: refresh,
  })
}

export function useRetryFailed(projectId: string) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (experimentId: string) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/experiments/{experiment_id}/retry-failed", {
          params: params({ projectId, experimentId }),
        }),
      ),
    onSettled: refresh,
  })
}
