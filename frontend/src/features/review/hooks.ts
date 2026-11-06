/** Review queue hooks: your queue, progress, people, giving answers out, labelling and settling disagreements. */
"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"
import type { LabelIn, ResolveRequest, ReviewAssignRequest } from "@/lib/api/types"

function path(projectId: string) {
  return { path: { project_id: projectId } }
}

export function useMyQueue(
  projectId: string,
  status: "open" | "done",
  experimentId: string | null,
  blind: boolean,
) {
  return useQuery({
    queryKey: ["projects", projectId, "review", "mine", status, experimentId, blind],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/review-queue/mine", {
          params: {
            ...path(projectId),
            query: { status, blind, limit: 50, ...(experimentId ? { experiment_id: experimentId } : {}) },
          },
        }),
      ),
  })
}

export function useReviewProgress(projectId: string, experimentId: string | null) {
  return useQuery({
    queryKey: ["projects", projectId, "review", "progress", experimentId],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/review-queue/progress", {
          params: { ...path(projectId), query: experimentId ? { experiment_id: experimentId } : {} },
        }),
      ),
  })
}

export function useReviewMembers(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "review", "members"],
    queryFn: () =>
      call(() => api.GET("/api/v1/projects/{project_id}/review-queue/members", { params: path(projectId) })),
  })
}

export function useDisputes(projectId: string, experimentId: string | null) {
  return useQuery({
    queryKey: ["projects", projectId, "review", "disputes", experimentId],
    enabled: Boolean(experimentId),
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/review-queue/disputes", {
          params: { ...path(projectId), query: { experiment_id: experimentId ?? "", include_settled: true } },
        }),
      ),
  })
}

export function useAssign(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ReviewAssignRequest) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/review-queue/assignments", {
          params: path(projectId),
          body,
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["projects", projectId, "review"] }),
  })
}

export function useLabelAnswer(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ experimentId, runId, body }: { experimentId: string; runId: string; body: LabelIn }) =>
      call(() =>
        api.PUT(
          "/api/v1/projects/{project_id}/experiments/{experiment_id}/answers/{test_case_run_id}/label",
          {
            params: {
              path: { project_id: projectId, experiment_id: experimentId, test_case_run_id: runId },
            },
            body,
          },
        ),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["projects", projectId, "review"] }),
  })
}

export function useResolve(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      experimentId,
      runId,
      body,
    }: {
      experimentId: string
      runId: string
      body: ResolveRequest
    }) =>
      call(() =>
        api.PUT(
          "/api/v1/projects/{project_id}/review-queue/disputes/{experiment_id}/{test_case_run_id}/resolution",
          {
            params: {
              path: { project_id: projectId, experiment_id: experimentId, test_case_run_id: runId },
            },
            body,
          },
        ),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["projects", projectId, "review"] }),
  })
}
