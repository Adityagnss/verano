/** Improve hooks: the latest session for an experiment (polled while it works), starting one, and accepting a candidate. */
"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"

const WORKING = new Set(["analyzing", "testing", "confirming"])

function path(projectId: string) {
  return { path: { project_id: projectId } }
}

export function useLatestSession(projectId: string, experimentId: string | null) {
  return useQuery({
    queryKey: ["projects", projectId, "improvement", experimentId],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/improvements/latest", {
          params: { ...path(projectId), query: { experiment_id: experimentId ?? "" } },
        }),
      ),
    enabled: experimentId !== null,
    refetchInterval: (query) => (query.state.data && WORKING.has(query.state.data.stage) ? 1500 : false),
  })
}

function useInvalidate(projectId: string) {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ["projects", projectId] })
}

export function useStartImprove(projectId: string) {
  const invalidate = useInvalidate(projectId)
  return useMutation({
    mutationFn: (experimentId: string) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/improvements", {
          params: path(projectId),
          body: { experiment_id: experimentId },
        }),
      ),
    onSettled: invalidate,
  })
}

export function useAccept(projectId: string) {
  const invalidate = useInvalidate(projectId)
  return useMutation({
    mutationFn: ({ sessionId, candidateId }: { sessionId: string; candidateId: string }) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/improvements/{session_id}/candidates/{candidate_id}/accept", {
          params: { path: { project_id: projectId, session_id: sessionId, candidate_id: candidateId } },
        }),
      ),
    onSettled: invalidate,
  })
}
