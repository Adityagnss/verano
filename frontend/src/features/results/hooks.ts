/** Results hooks: one experiment's per-model metrics, its case view, and the CSV download. */
"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"
import type { EvaluatorConfigIn, JudgeChoice } from "@/lib/api/types"

function experimentPath(projectId: string, experimentId: string) {
  return { path: { project_id: projectId, experiment_id: experimentId } }
}

const SCORING = new Set(["pending", "running"])

/** True while the results are not there yet (first scoring) or a new scoring pass is queued or running. */
export function scoringInProgress(results: {
  evaluation_run: unknown
  evaluation_runs: { status: string }[]
}) {
  return !results.evaluation_run || results.evaluation_runs.some((r) => SCORING.has(r.status))
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
    refetchInterval: (query) => (query.state.data && scoringInProgress(query.state.data) ? 1500 : false),
  })
}

export function useCases(
  projectId: string,
  experimentId: string | null,
  failedOnly: boolean,
  enabled: boolean,
  evaluationRunId: string | null = null,
) {
  return useQuery({
    queryKey: ["projects", projectId, "result-cases", experimentId, failedOnly, evaluationRunId],
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
    mutationFn: ({
      experimentId,
      judge,
      evaluators,
    }: {
      experimentId: string
      judge?: JudgeChoice | null
      evaluators?: EvaluatorConfigIn[] | null
    }) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/experiments/{experiment_id}/rescore", {
          params: experimentPath(projectId, experimentId),
          body: { ...(judge ? { judge } : {}), ...(evaluators ? { evaluators } : {}) },
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["projects", projectId] }),
  })
}

/** The model Verano suggests as judge (the strongest priced one that is not being tested) and every possible choice. */
export function useJudgeSuggestion(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "judge-suggestion"],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/judge/suggestion", {
          params: { path: { project_id: projectId } },
        }),
      ),
  })
}

/** What scoring an experiment again with a judge would cost, before anything is asked. */
export function useRescoreEstimate(
  projectId: string,
  experimentId: string | null,
  judge: JudgeChoice | null,
  evaluators: EvaluatorConfigIn[] | null = null,
) {
  return useQuery({
    queryKey: ["projects", projectId, "rescore-estimate", experimentId, judge, evaluators],
    queryFn: () =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/experiments/{experiment_id}/rescore/estimate", {
          params: experimentPath(projectId, experimentId ?? ""),
          body: { ...(judge ? { judge } : {}), ...(evaluators ? { evaluators } : {}) },
        }),
      ),
    enabled: experimentId !== null,
    retry: false,
  })
}

/** The checks (criteria, steps, thresholds) and judge of one evaluator-set version. */
export function useEvaluatorVersion(projectId: string, versionId: string | null) {
  return useQuery({
    queryKey: ["projects", projectId, "evaluator-version", versionId],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/evaluator-set-versions/{version_id}", {
          params: { path: { project_id: projectId, version_id: versionId ?? "" } },
        }),
      ),
    enabled: versionId !== null,
  })
}

/** Every call the judge made about one answer, exactly as sent (loaded when asked for). */
export function useJudgeCalls(projectId: string, experimentId: string, answerId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["projects", projectId, "judge-calls", experimentId, answerId],
    queryFn: () =>
      call(() =>
        api.GET(
          "/api/v1/projects/{project_id}/experiments/{experiment_id}/answers/{test_case_run_id}/judge-calls",
          {
            params: {
              path: { project_id: projectId, experiment_id: experimentId, test_case_run_id: answerId },
            },
          },
        ),
      ),
    enabled,
  })
}

type TryBody = { test_case_run_id: string; evaluator: EvaluatorConfigIn; judge?: JudgeChoice | null }

function tryBody({ judge, ...rest }: TryBody) {
  return judge ? { ...rest, judge } : rest
}

/** What trying the judge on one answer would cost. */
export function useTryEstimate(projectId: string, experimentId: string | null, body: TryBody | null) {
  return useQuery({
    queryKey: ["projects", projectId, "try-estimate", experimentId, body],
    queryFn: () =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/experiments/{experiment_id}/judge/try/estimate", {
          params: experimentPath(projectId, experimentId ?? ""),
          body: tryBody(body!),
        }),
      ),
    enabled: experimentId !== null && body !== null,
    retry: false,
  })
}

/** Runs one judged check on one stored answer; nothing is scored or changed. */
export function useTryJudge(projectId: string, experimentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: TryBody) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/experiments/{experiment_id}/judge/try", {
          params: experimentPath(projectId, experimentId),
          body: tryBody(body),
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["projects", projectId, "judge-calls"] }),
  })
}
