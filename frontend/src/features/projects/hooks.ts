/**
 * Project hooks: list, create, one project, its running cost, and step completion (a key
 * with selected models, a saved prompt, imported data, approved test cases, an experiment
 * started, one finished and scored, an improvement tested).
 */
"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"

export function useProjects(enabled = true) {
  return useQuery({
    enabled,
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

async function optional<T>(send: () => Promise<T>): Promise<T | null> {
  try {
    return await send()
  } catch {
    return null
  }
}

export function useStepCompletion(projectId: string) {
  const params = { params: { path: { project_id: projectId } } }
  return useQuery({
    queryKey: ["projects", projectId, "step-completion"],
    queryFn: async () => {
      const [models, prompts, files, version, experiments] = await Promise.all([
        call(() =>
          api.GET("/api/v1/projects/{project_id}/models", {
            params: { path: { project_id: projectId }, query: { selected: true, limit: 1 } },
          }),
        ),
        call(() =>
          api.GET("/api/v1/projects/{project_id}/prompts", {
            params: { path: { project_id: projectId }, query: { limit: 1 } },
          }),
        ),
        call(() =>
          api.GET("/api/v1/projects/{project_id}/input-files", {
            params: { path: { project_id: projectId }, query: { limit: 100 } },
          }),
        ),
        optional(() => call(() => api.GET("/api/v1/projects/{project_id}/dataset-versions/current", params))),
        call(() =>
          api.GET("/api/v1/projects/{project_id}/experiments", {
            params: { path: { project_id: projectId }, query: { limit: 20 } },
          }),
        ),
      ])
      const manual = experiments.items.filter((e) => e.origin === "manual")
      return {
        keys: models.items.length > 0,
        prompt: prompts.items.length > 0,
        data: files.items.some((file) => file.status === "imported" || file.status === "extracted"),
        tests: version?.status === "approved",
        run: manual.length > 0,
        results: manual.some((e) => e.status === "completed"),
        improve: experiments.items.some((e) => e.origin === "optimization" && e.status === "completed"),
      }
    },
  })
}
