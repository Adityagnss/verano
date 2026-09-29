/** Logbook data: filter options, answers, one answer in full, analysis, model calls. */
"use client"

import { keepPreviousData, useQuery } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"

import { type AnswerFilters, type CallFilters, toParams } from "./domain"

function base(projectId: string) {
  return { path: { project_id: projectId } }
}

export type Paging = { sort: string; order: "asc" | "desc"; offset: number; limit: number }

export function useLogOptions(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "logbook", "options"],
    queryFn: () =>
      call(() => api.GET("/api/v1/projects/{project_id}/logbook/options", { params: base(projectId) })),
  })
}

export function useAnswers(projectId: string, filters: AnswerFilters, paging: Paging) {
  return useQuery({
    queryKey: ["projects", projectId, "logbook", "answers", filters, paging],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/logbook/answers", {
          params: { ...base(projectId), query: { ...toParams(filters), ...paging } as never },
        }),
      ),
    placeholderData: keepPreviousData,
  })
}

export function useAnswer(projectId: string, experimentId: string | null, runId: string | null) {
  return useQuery({
    queryKey: ["projects", projectId, "logbook", "answer", experimentId, runId],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/logbook/answers/{experiment_id}/{run_id}", {
          params: { path: { project_id: projectId, experiment_id: experimentId ?? "", run_id: runId ?? "" } },
        }),
      ),
    enabled: experimentId !== null && runId !== null,
  })
}

export function useAnalysis(projectId: string, filters: AnswerFilters, enabled: boolean) {
  return useQuery({
    queryKey: ["projects", projectId, "logbook", "analysis", filters],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/logbook/analysis", {
          params: { ...base(projectId), query: toParams(filters) as never },
        }),
      ),
    enabled,
    placeholderData: keepPreviousData,
  })
}

export function useCalls(
  projectId: string,
  filters: CallFilters,
  offset: number,
  limit: number,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["projects", projectId, "logbook", "calls", filters, offset, limit],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/logbook/calls", {
          params: { ...base(projectId), query: { ...toParams(filters), offset, limit } as never },
        }),
      ),
    enabled,
    placeholderData: keepPreviousData,
  })
}

export function useCall(projectId: string, callId: string | null) {
  return useQuery({
    queryKey: ["projects", projectId, "logbook", "call", callId],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/logbook/calls/{call_id}", {
          params: { path: { project_id: projectId, call_id: callId ?? "" } },
        }),
      ),
    enabled: callId !== null,
  })
}

export async function downloadLogbookCsv(
  projectId: string,
  filters: AnswerFilters,
  paging: Paging,
): Promise<void> {
  const text = await call(() =>
    api.GET("/api/v1/projects/{project_id}/logbook/answers.csv", {
      params: {
        ...base(projectId),
        query: { ...toParams(filters), sort: paging.sort, order: paging.order } as never,
      },
      parseAs: "text",
    }),
  )
  const url = URL.createObjectURL(new Blob([text as unknown as string], { type: "text/csv" }))
  const link = document.createElement("a")
  link.href = url
  link.download = "verano-logbook.csv"
  link.click()
  URL.revokeObjectURL(url)
}
