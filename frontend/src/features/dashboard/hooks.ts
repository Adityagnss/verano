/** Dashboard data: experiments, each finished experiment's results, prompt versions, spend. */
"use client"

import { useQueries, useQuery } from "@tanstack/react-query"

import { useExperiments } from "@/features/run/hooks"
import { useCostSummary } from "@/features/projects/hooks"
import { api, call } from "@/lib/api/client"
import type { ResultsOut } from "@/lib/api/types"

function usePromptVersions(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "prompt-versions"],
    queryFn: async () => {
      const prompts = await call(() =>
        api.GET("/api/v1/projects/{project_id}/prompts", {
          params: { path: { project_id: projectId }, query: { limit: 20 } },
        }),
      )
      const lists = await Promise.all(
        prompts.items.map((prompt) =>
          call(() =>
            api.GET("/api/v1/projects/{project_id}/prompts/{prompt_id}/versions", {
              params: { path: { project_id: projectId, prompt_id: prompt.id }, query: { limit: 100 } },
            }),
          ),
        ),
      )
      return lists.flatMap((list) => list.items)
    },
  })
}

export function useDashboardData(projectId: string) {
  const experiments = useExperiments(projectId)
  const cost = useCostSummary(projectId)
  const versions = usePromptVersions(projectId)
  const completed = (experiments.data ?? []).filter((e) => e.status === "completed").slice(0, 10)
  const results = useQueries({
    queries: completed.map((experiment) => ({
      queryKey: ["projects", projectId, "results", experiment.id],
      queryFn: () =>
        call(() =>
          api.GET("/api/v1/projects/{project_id}/experiments/{experiment_id}/results", {
            params: { path: { project_id: projectId, experiment_id: experiment.id } },
          }),
        ),
    })),
  })
  const byExperiment = new Map<string, ResultsOut>()
  results.forEach((query, index) => {
    if (query.data) byExperiment.set(completed[index].id, query.data)
  })
  return {
    experiments: experiments.data ?? [],
    cost: cost.data,
    versions: versions.data ?? [],
    results: byExperiment,
    loading: experiments.isPending || results.some((q) => q.isPending),
    error: experiments.error ?? cost.error ?? versions.error ?? results.find((q) => q.error)?.error ?? null,
  }
}
