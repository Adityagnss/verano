/** Hooks for adding checks: the judge gallery, the rule catalogue, the code check contract and "try it". */
"use client"

import { useMutation, useQuery } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"

const path = (projectId: string) => ({ path: { project_id: projectId } })

export function useJudgeGallery(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "judge-gallery"],
    queryFn: () =>
      call(() => api.GET("/api/v1/projects/{project_id}/judge-gallery", { params: path(projectId) })),
    staleTime: 60_000,
  })
}

export function useRuleChecks(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "rule-checks"],
    queryFn: () =>
      call(() => api.GET("/api/v1/projects/{project_id}/rule-checks", { params: path(projectId) })),
    staleTime: 60_000,
  })
}

export function useCodeContract(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "code-contract"],
    queryFn: () =>
      call(() => api.GET("/api/v1/projects/{project_id}/code-checks/contract", { params: path(projectId) })),
    staleTime: 60_000,
  })
}

export type TryInput = {
  code: string
  output: string
  expected: string | null
  inputs: Record<string, string>
}

/** Runs the code on one sample answer in the sandbox. Nothing is saved. */
export function useTryCode(projectId: string) {
  return useMutation({
    mutationFn: (body: TryInput) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/code-checks/try", { params: path(projectId), body }),
      ),
  })
}

/** The two numbers behind the words "clearly better" and "proven". */
export function useEvidenceThresholds(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "evidence-thresholds"],
    queryFn: () =>
      call(() => api.GET("/api/v1/projects/{project_id}/evidence-thresholds", { params: path(projectId) })),
    staleTime: 300_000,
  })
}
