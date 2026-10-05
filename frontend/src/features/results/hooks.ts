/** Results hooks: one experiment's per-model metrics, its case view, and the CSV download. */
"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"

function experimentPath(projectId: string, experimentId: string) {
  return { path: { project_id: projectId, experiment_id: experimentId } }
}

export function useResults(projectId: string, experimentId: string | null) {
  return useQuery({
    queryKey: ["projects", projectId, "results", experimentId],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/experiments/{experiment_id}/results", {
          params: experimentPath(projectId, experimentId ?? ""),
        }),
      ),
    enabled: experimentId !== null,
    refetchInterval: (query) => (query.state.data && !query.state.data.evaluation_run ? 1500 : false),
  })
}

export function useCases(
  projectId: string,
  experimentId: string | null,
  failedOnly: boolean,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["projects", projectId, "result-cases", experimentId, failedOnly],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/experiments/{experiment_id}/cases", {
          params: { ...experimentPath(projectId, experimentId ?? ""), query: { failed_only: failedOnly } },
        }),
      ),
    enabled: enabled && experimentId !== null,
  })
}

export async function downloadCsv(projectId: string, experimentId: string): Promise<void> {
  const text = await call(() =>
    api.GET("/api/v1/projects/{project_id}/experiments/{experiment_id}/export.csv", {
      params: experimentPath(projectId, experimentId),
      parseAs: "text",
    }),
  )
  const url = URL.createObjectURL(new Blob([text as unknown as string], { type: "text/csv" }))
  const link = document.createElement("a")
  link.href = url
  link.download = `experiment-${experimentId}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

/** Did this experiment answer like an earlier one with the same configuration? */
export function useReplication(projectId: string, experimentId: string, againstId: string | null) {
  return useQuery({
    queryKey: ["projects", projectId, "replication", experimentId, againstId],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/experiments/{experiment_id}/replication", {
          params: { ...experimentPath(projectId, experimentId), query: { against: againstId ?? "" } },
        }),
      ),
    enabled: againstId !== null,
    retry: false,
  })
}

/** A new experiment with the same configuration as this one. */
export function useRerun(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (experimentId: string) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/experiments/{experiment_id}/rerun", {
          params: experimentPath(projectId, experimentId),
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["projects", projectId] }),
  })
}

/** Score every answer of an experiment again with its evaluator set (a new evaluation run; the old one is kept). */
export function useScoreAgain(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (experimentId: string) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/experiments/{experiment_id}/rescore", {
          params: experimentPath(projectId, experimentId),
          body: {},
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["projects", projectId] }),
  })
}
