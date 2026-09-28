/**
 * Run step hooks: the cost preview for a configuration, starting and stopping an
 * experiment, and the project's experiments (the latest is polled while it runs).
 */
"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"
import type { ExperimentCreate } from "@/lib/api/types"

const POLL_MS = 1000
const ACTIVE = new Set(["planned", "running", "evaluating"])

function path(projectId: string) {
  return { path: { project_id: projectId } }
}

export function useExperiments(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "experiments"],
    queryFn: async () =>
      (
        await call(() =>
          api.GET("/api/v1/projects/{project_id}/experiments", {
            params: { ...path(projectId), query: { limit: 50 } },
          }),
        )
      ).items,
    refetchInterval: (query) =>
      (query.state.data ?? []).some((e) => ACTIVE.has(e.status)) ? POLL_MS : false,
  })
}

export function useExperimentEstimate(projectId: string, body: ExperimentCreate | null) {
  return useQuery({
    queryKey: ["projects", projectId, "experiment-estimate", body],
    queryFn: () =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/experiments/estimate", {
          params: path(projectId),
          body: body!,
        }),
      ),
    enabled: body !== null,
    retry: false,
  })
}

function useInvalidate(projectId: string) {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ["projects", projectId] })
}

export function useStartExperiment(projectId: string) {
  const invalidate = useInvalidate(projectId)
  return useMutation({
    mutationFn: (body: ExperimentCreate) =>
      call(() => api.POST("/api/v1/projects/{project_id}/experiments", { params: path(projectId), body })),
    onSettled: invalidate,
  })
}

export function useCancelExperiment(projectId: string) {
  const invalidate = useInvalidate(projectId)
  return useMutation({
    mutationFn: (experimentId: string) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/experiments/{experiment_id}/cancel", {
          params: { path: { project_id: projectId, experiment_id: experimentId } },
        }),
      ),
    onSettled: invalidate,
  })
}
