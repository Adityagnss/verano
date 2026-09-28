/**
 * Prompt step hooks: the project's prompt (the newest one; V1 tests one prompt per
 * project), the live check of the draft, and saving a new immutable version.
 */
"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"

function path(projectId: string) {
  return { path: { project_id: projectId } }
}

export function useCurrentPrompt(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "prompt"],
    queryFn: async () => {
      const page = await call(() =>
        api.GET("/api/v1/projects/{project_id}/prompts", {
          params: { ...path(projectId), query: { limit: 1 } },
        }),
      )
      return page.items[0] ?? null
    },
  })
}

export type Draft = {
  name: string
  system_template: string
  user_template: string
  temperature: string
  max_tokens: string
  change_reason: string
}

export function defaultParams(draft: Draft): Record<string, number> {
  const params: Record<string, number> = {}
  if (draft.temperature.trim()) params.temperature = Number(draft.temperature)
  if (draft.max_tokens.trim()) params.max_tokens = Number(draft.max_tokens)
  return params
}

export function useInspect(
  projectId: string,
  draft: Draft,
  modelIds: string[],
  sample: Record<string, unknown> | null,
) {
  const system = draft.system_template.trim() ? draft.system_template : null
  const user = draft.user_template.trim() ? draft.user_template : null
  const body = {
    system_template: system,
    user_template: user,
    model_profile_ids: modelIds,
    sample_inputs: sample,
    max_tokens: draft.max_tokens.trim() ? Number(draft.max_tokens) : null,
  }
  return useQuery({
    queryKey: ["projects", projectId, "prompt-inspect", body],
    queryFn: () =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/prompts/inspect", { params: path(projectId), body }),
      ),
    enabled: system !== null || user !== null,
    placeholderData: (previous) => previous,
    retry: false,
  })
}

export function useSavePrompt(projectId: string, promptId: string | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (draft: Draft) => {
      const templates = {
        system_template: draft.system_template.trim() ? draft.system_template : null,
        user_template: draft.user_template.trim() ? draft.user_template : null,
        default_params: defaultParams(draft),
        change_reason: draft.change_reason.trim() || null,
      }
      if (promptId === null) {
        const created = await call(() =>
          api.POST("/api/v1/projects/{project_id}/prompts", {
            params: path(projectId),
            body: { name: draft.name.trim() || "Prompt", ...templates },
          }),
        )
        return created.latest_version
      }
      return call(() =>
        api.POST("/api/v1/projects/{project_id}/prompts/{prompt_id}/versions", {
          params: { path: { project_id: projectId, prompt_id: promptId } },
          body: templates,
        }),
      )
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["projects", projectId] }),
  })
}
