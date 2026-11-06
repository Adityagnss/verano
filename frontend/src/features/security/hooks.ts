/** Security hooks: attack families, packs and their cases, running a pack, the report, and "harden". */
"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"
import type { JudgeChoice } from "@/lib/api/types"

const base = (projectId: string) => ({ path: { project_id: projectId } })
const packPath = (projectId: string, packId: string) => ({ path: { project_id: projectId, pack_id: packId } })

export function useFamilies(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "security", "families"],
    queryFn: () =>
      call(() => api.GET("/api/v1/projects/{project_id}/security/families", { params: base(projectId) })),
  })
}

export function usePacks(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "security", "packs"],
    queryFn: () =>
      call(() => api.GET("/api/v1/projects/{project_id}/security/packs", { params: base(projectId) })),
    refetchInterval: (query) =>
      (query.state.data ?? []).some((p) => p.status === "generating") ? 1500 : false,
  })
}

export function usePack(projectId: string, packId: string | null) {
  return useQuery({
    queryKey: ["projects", projectId, "security", "pack", packId],
    enabled: packId !== null,
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/security/packs/{pack_id}", {
          params: packPath(projectId, packId ?? ""),
        }),
      ),
    refetchInterval: (query) => (query.state.data?.status === "generating" ? 1500 : false),
  })
}

export function useReport(projectId: string, packId: string | null, experimentId: string | null) {
  return useQuery({
    queryKey: ["projects", projectId, "security", "report", packId, experimentId],
    enabled: packId !== null && experimentId !== null,
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/security/packs/{pack_id}/report", {
          params: { ...packPath(projectId, packId ?? ""), query: { experiment_id: experimentId ?? "" } },
        }),
      ),
    refetchInterval: (query) => (query.state.data?.experiment_status === "completed" ? false : 3000),
  })
}

function useRefresh(projectId: string) {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ["projects", projectId] })
}

export function useCreatePack(projectId: string) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (body: {
      prompt_version_id: string
      per_category: number
      tool_app: boolean
      generator: JudgeChoice | null
    }) =>
      call(() => api.POST("/api/v1/projects/{project_id}/security/packs", { params: base(projectId), body })),
    onSettled: refresh,
  })
}

export function useReviewCase(projectId: string, packId: string) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: ({ caseId, status }: { caseId: string; status: "approved" | "rejected" }) =>
      call(() =>
        api.PATCH("/api/v1/projects/{project_id}/security/packs/{pack_id}/cases/{case_id}", {
          params: { path: { project_id: projectId, pack_id: packId, case_id: caseId } },
          body: { status },
        }),
      ),
    onSettled: refresh,
  })
}

export function useReviewAll(projectId: string, packId: string) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (category: string | null) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/security/packs/{pack_id}/review", {
          params: packPath(projectId, packId),
          body: { category, status: "approved" },
        }),
      ),
    onSettled: refresh,
  })
}

export function useApprovePack(projectId: string, packId: string) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: () =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/security/packs/{pack_id}/approve", {
          params: packPath(projectId, packId),
        }),
      ),
    onSettled: refresh,
  })
}

export function useRunPack(projectId: string, packId: string) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (body: {
      models: { model_profile_id: string; runs: number; params: Record<string, number> }[]
      judge: JudgeChoice
    }) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/security/packs/{pack_id}/runs", {
          params: packPath(projectId, packId),
          body,
        }),
      ),
    onSettled: refresh,
  })
}

export function useHarden(projectId: string, packId: string) {
  const refresh = useRefresh(projectId)
  return useMutation({
    mutationFn: (experimentId: string) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/security/packs/{pack_id}/harden", {
          params: packPath(projectId, packId),
          body: { experiment_id: experimentId },
        }),
      ),
    onSettled: refresh,
  })
}
