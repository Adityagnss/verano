/** Apps hooks: the project's connected apps, adding, removing and trying one. */
"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"
import type { components } from "@/lib/api/schema"
import type { AppTargetCreate } from "@/lib/api/types"

type AppTargetUpdate = components["schemas"]["AppTargetUpdate"]

export function useApps(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "apps"],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/apps", { params: { path: { project_id: projectId } } }),
      ),
  })
}

export function useAddApp(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: AppTargetCreate) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/apps", { params: { path: { project_id: projectId } }, body }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["projects", projectId] }),
  })
}

export function useRemoveApp(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (appId: string) =>
      call(() =>
        api.DELETE("/api/v1/projects/{project_id}/apps/{app_id}", {
          params: { path: { project_id: projectId, app_id: appId } },
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["projects", projectId] }),
  })
}

export function useTryApp(projectId: string) {
  return useMutation({
    mutationFn: ({ appId, inputs }: { appId: string; inputs: Record<string, string> }) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/apps/{app_id}/test", {
          params: { path: { project_id: projectId, app_id: appId } },
          body: { inputs },
        }),
      ),
  })
}

export function useChangeApp(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ appId, body }: { appId: string; body: AppTargetUpdate }) =>
      call(() =>
        api.PATCH("/api/v1/projects/{project_id}/apps/{app_id}", {
          params: { path: { project_id: projectId, app_id: appId } },
          body,
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["projects", projectId] }),
  })
}
