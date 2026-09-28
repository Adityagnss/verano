/**
 * Test Cases hooks: the current dataset version (polled while generating), its cases, the
 * Task Spec, the generator-model suggestion and cost preview, generation, review actions,
 * approval, and the evaluator set.
 */
"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { ApiError, api, call } from "@/lib/api/client"
import type {
  EvaluatorConfigIn,
  GenerationRequest,
  ItemOut,
  ItemSource,
  ItemUpdate,
  TaskSpec,
} from "@/lib/api/types"

const PAGE_SIZE = 200
const POLL_MS = 1500

function path(projectId: string) {
  return { path: { project_id: projectId } }
}

function versionPath(projectId: string, versionId: string) {
  return { path: { project_id: projectId, version_id: versionId } }
}

export function useCurrentVersion(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "dataset-version"],
    queryFn: async () => {
      try {
        return await call(() =>
          api.GET("/api/v1/projects/{project_id}/dataset-versions/current", { params: path(projectId) }),
        )
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null
        throw error
      }
    },
    refetchInterval: (query) => (query.state.data?.generation?.status === "running" ? POLL_MS : false),
  })
}

async function allItems(projectId: string, versionId: string, source?: ItemSource): Promise<ItemOut[]> {
  const items: ItemOut[] = []
  let cursor: string | undefined
  do {
    const page = await call(() =>
      api.GET("/api/v1/projects/{project_id}/dataset-versions/{version_id}/items", {
        params: { ...versionPath(projectId, versionId), query: { limit: PAGE_SIZE, cursor, source } },
      }),
    )
    items.push(...page.items)
    cursor = page.next_cursor ?? undefined
  } while (cursor)
  return items
}

export function useItems(projectId: string, versionId: string | undefined, running: boolean) {
  return useQuery({
    queryKey: ["projects", projectId, "items", versionId],
    queryFn: () => allItems(projectId, versionId ?? ""),
    enabled: versionId !== undefined,
    refetchInterval: running ? POLL_MS : false,
  })
}

export function useFirstCase(projectId: string) {
  const version = useCurrentVersion(projectId)
  const versionId = version.data?.id
  return useQuery({
    queryKey: ["projects", projectId, "first-case", versionId],
    queryFn: async () => {
      const page = await call(() =>
        api.GET("/api/v1/projects/{project_id}/dataset-versions/{version_id}/items", {
          params: { ...versionPath(projectId, versionId ?? ""), query: { limit: 1 } },
        }),
      )
      return page.items[0] ?? null
    },
    enabled: versionId !== undefined,
  })
}

export function useTaskSpec(projectId: string, specId: string | null | undefined) {
  return useQuery({
    queryKey: ["projects", projectId, "task-spec", specId],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/task-specs/{spec_id}", {
          params: { path: { project_id: projectId, spec_id: specId ?? "" } },
        }),
      ),
    enabled: Boolean(specId),
  })
}

export function useGeneratorSuggestion(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "generator-suggestion"],
    queryFn: () =>
      call(() => api.GET("/api/v1/projects/{project_id}/generator/suggestion", { params: path(projectId) })),
  })
}

export function useEstimate(projectId: string, body: GenerationRequest | null) {
  return useQuery({
    queryKey: ["projects", projectId, "generation-estimate", body],
    queryFn: () =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/generations/estimate", {
          params: path(projectId),
          body: body!,
        }),
      ),
    enabled: body !== null,
    retry: false,
  })
}

function useInvalidate(projectId: string) {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ["projects", projectId] })
}

export function useDraftSpec(projectId: string) {
  const invalidate = useInvalidate(projectId)
  return useMutation({
    mutationFn: (body: { prompt_version_id: string; credential_id: string; model: string }) =>
      call(() => api.POST("/api/v1/projects/{project_id}/task-specs", { params: path(projectId), body })),
    onSettled: invalidate,
  })
}

export function useConfirmSpec(projectId: string) {
  const invalidate = useInvalidate(projectId)
  return useMutation({
    mutationFn: ({ specId, spec }: { specId: string; spec: TaskSpec }) =>
      call(() =>
        api.PUT("/api/v1/projects/{project_id}/task-specs/{spec_id}", {
          params: { path: { project_id: projectId, spec_id: specId } },
          body: { spec },
        }),
      ),
    onSettled: invalidate,
  })
}

export function useStartGeneration(projectId: string) {
  const invalidate = useInvalidate(projectId)
  return useMutation({
    mutationFn: (body: GenerationRequest) =>
      call(() => api.POST("/api/v1/projects/{project_id}/generations", { params: path(projectId), body })),
    onSettled: invalidate,
  })
}

export function useVersionActions(projectId: string, versionId: string) {
  const invalidate = useInvalidate(projectId)
  const params = versionPath(projectId, versionId)
  const itemParams = (itemId: string) => ({ path: { ...params.path, item_id: itemId } })
  return {
    regenerate: useMutation({
      mutationFn: (category: string) =>
        call(() =>
          api.POST("/api/v1/projects/{project_id}/dataset-versions/{version_id}/regenerate", {
            params,
            body: { category: category as never },
          }),
        ),
      onSettled: invalidate,
    }),
    editItem: useMutation({
      mutationFn: ({ itemId, body }: { itemId: string; body: ItemUpdate }) =>
        call(() =>
          api.PATCH("/api/v1/projects/{project_id}/dataset-versions/{version_id}/items/{item_id}", {
            params: itemParams(itemId),
            body,
          }),
        ),
      onSettled: invalidate,
    }),
    deleteItem: useMutation({
      mutationFn: (itemId: string) =>
        call(() =>
          api.DELETE("/api/v1/projects/{project_id}/dataset-versions/{version_id}/items/{item_id}", {
            params: itemParams(itemId),
          }),
        ),
      onSettled: invalidate,
    }),
    approveDrafts: useMutation({
      mutationFn: (category: string) =>
        call(() =>
          api.POST("/api/v1/projects/{project_id}/dataset-versions/{version_id}/approve-drafts", {
            params,
            body: { category },
          }),
        ),
      onSettled: invalidate,
    }),
    approve: useMutation({
      mutationFn: () =>
        call(() =>
          api.POST("/api/v1/projects/{project_id}/dataset-versions/{version_id}/approve", { params }),
        ),
      onSettled: invalidate,
    }),
  }
}

export function useEvaluators(projectId: string, versionId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["projects", projectId, "evaluators", versionId],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/dataset-versions/{version_id}/evaluators", {
          params: versionPath(projectId, versionId ?? ""),
        }),
      ),
    enabled: enabled && versionId !== undefined,
  })
}

export function useEditEvaluators(projectId: string, versionId: string) {
  const invalidate = useInvalidate(projectId)
  return useMutation({
    mutationFn: (evaluators: EvaluatorConfigIn[]) =>
      call(() =>
        api.PUT("/api/v1/projects/{project_id}/dataset-versions/{version_id}/evaluators", {
          params: versionPath(projectId, versionId),
          body: { evaluators, change_reason: "Edited on the Test Cases screen" },
        }),
      ),
    onSettled: invalidate,
  })
}
