/** Improve hooks: the latest session for an experiment (polled while it works), starting one, and accepting a candidate. */
"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"
import type { JudgeChoice } from "@/lib/api/types"

const WORKING = new Set(["analyzing", "quick", "testing", "confirming"])

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
    mutationFn: ({ experimentId, writer }: { experimentId: string; writer: JudgeChoice | null }) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/improvements", {
          params: path(projectId),
          body: { experiment_id: experimentId, writer },
        }),
      ),
    onSettled: invalidate,
  })
}

/** Accept a proven candidate as the new version and test it on all test cases right away. */
export function useAccept(projectId: string) {
  const invalidate = useInvalidate(projectId)
  return useMutation({
    mutationFn: ({ sessionId, candidateId }: { sessionId: string; candidateId: string }) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/improvements/{session_id}/candidates/{candidate_id}/accept", {
          params: {
            path: { project_id: projectId, session_id: sessionId, candidate_id: candidateId },
            query: { run: true },
          },
        }),
      ),
    onSettled: invalidate,
  })
}

/** Earlier improvements of the project, newest first. */
export function useImprovementHistory(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "improvement-history"],
    queryFn: () =>
      call(() => api.GET("/api/v1/projects/{project_id}/improvements", { params: path(projectId) })),
  })
}

/** One improvement session, opened from the history. */
export function useImprovement(projectId: string, sessionId: string | null) {
  return useQuery({
    queryKey: ["projects", projectId, "improvement", sessionId],
    enabled: sessionId !== null,
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/improvements/{session_id}", {
          params: { path: { project_id: projectId, session_id: sessionId ?? "" } },
        }),
      ),
  })
}

/** The candidate an experiment was testing, if it was one of Improve's tests. */
export function useCandidateFor(projectId: string, experimentId: string | null) {
  return useQuery({
    queryKey: ["projects", projectId, "candidate-for", experimentId],
    enabled: experimentId !== null,
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/improvements/candidate-for/{experiment_id}", {
          params: { path: { project_id: projectId, experiment_id: experimentId ?? "" } },
        }),
      ),
  })
}

function useSessionAction(projectId: string, action: "stop" | "continue") {
  const invalidate = useInvalidate(projectId)
  return useMutation({
    mutationFn: (sessionId: string) =>
      call(() =>
        api.POST(`/api/v1/projects/{project_id}/improvements/{session_id}/${action}`, {
          params: { path: { project_id: projectId, session_id: sessionId } },
        }),
      ),
    onSettled: invalidate,
  })
}

/** Stop a running improvement where it is; nothing is deleted. */
export const useStopImprove = (projectId: string) => useSessionAction(projectId, "stop")

/** Carry on from where a stopped or failed improvement left off. */
export const useContinueImprove = (projectId: string) => useSessionAction(projectId, "continue")

/** Save any candidate as a normal prompt version (so it shows on the Prompt and Run steps); with `run`, test it on
 * all test cases right away. */
export function useSaveCandidate(projectId: string) {
  const invalidate = useInvalidate(projectId)
  return useMutation({
    mutationFn: ({ sessionId, candidateId, run }: { sessionId: string; candidateId: string; run: boolean }) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/improvements/{session_id}/candidates/{candidate_id}/save", {
          params: {
            path: { project_id: projectId, session_id: sessionId, candidate_id: candidateId },
            query: { run },
          },
        }),
      ),
    onSettled: invalidate,
  })
}
