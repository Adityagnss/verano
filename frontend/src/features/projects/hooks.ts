/** Project hooks: list, create, one project, its running cost, and step completion. */
"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"

export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: () => call(() => api.GET("/api/v1/projects", { params: { query: { limit: 100 } } })),
  })
}

export function useCreateProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => call(() => api.POST("/api/v1/projects", { body: { name } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["projects"] }),
  })
}

export function useProject(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId],
    queryFn: () =>
      call(() => api.GET("/api/v1/projects/{project_id}", { params: { path: { project_id: projectId } } })),
  })
}

export function useCostSummary(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "cost"],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/llm-calls/summary", {
          params: { path: { project_id: projectId } },
        }),
      ),
  })
}

export function useStepCompletion(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "models", "selected-count"],
    queryFn: async () => {
      const page = await call(() =>
        api.GET("/api/v1/projects/{project_id}/models", {
          params: { path: { project_id: projectId }, query: { selected: true, limit: 1 } },
        }),
      )
      return { keys: page.items.length > 0 }
    },
  })
}
