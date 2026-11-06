/** Traffic hooks: the list, import, making cases, settings, tokens, the daily score line and alerts. */
"use client"

import {
  type InfiniteData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"

import type { ChannelCreate, ConfigUpdate, RuleCreate, TraceFilters, TraceSummary } from "./types"

const BASE = "/api/v1/projects/{project_id}/traffic"

type TracePage = { items: TraceSummary[]; next_cursor: string | null }

function key(projectId: string, ...rest: unknown[]) {
  return ["projects", projectId, "traffic", ...rest]
}

function activeFilters(filters: TraceFilters) {
  return {
    failed: filters.failed,
    low_rated: filters.low_rated,
    long: filters.long,
    new_topic: filters.new_topic,
    unused: filters.unused,
    q: filters.q.trim() || null,
  }
}

export function useTraces(projectId: string, filters: TraceFilters) {
  return useInfiniteQuery<TracePage, Error, InfiniteData<TracePage>, unknown[], string | undefined>({
    queryKey: key(projectId, "list", filters),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    queryFn: ({ pageParam }) =>
      call(() =>
        api.GET(BASE, {
          params: {
            path: { project_id: projectId },
            query: {
              ...activeFilters(filters),
              q: filters.q.trim() || undefined,
              cursor: pageParam,
              limit: 50,
            },
          },
        }),
      ),
  })
}

export function useTrace(projectId: string, traceId: string | null) {
  return useQuery({
    queryKey: key(projectId, "trace", traceId),
    enabled: traceId !== null,
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/traffic/{trace_id}", {
          params: { path: { project_id: projectId, trace_id: traceId as string } },
        }),
      ),
  })
}

export function useFormats(projectId: string) {
  return useQuery({
    queryKey: key(projectId, "formats"),
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/traffic/formats", {
          params: { path: { project_id: projectId } },
        }),
      ),
  })
}

export function useImport(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ file, format, promptVersion }: { file: File; format: string; promptVersion: string }) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/traffic/import", {
          params: { path: { project_id: projectId } },
          body: { file: file as unknown as string, format, prompt_version: promptVersion || null },
          bodySerializer: (body) => {
            const form = new FormData()
            form.append("file", body.file as unknown as File)
            form.append("format", body.format ?? "auto")
            if (body.prompt_version) form.append("prompt_version", body.prompt_version)
            return form
          },
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: key(projectId) }),
  })
}

export function useMakeCases(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      trace_ids?: string[]
      filter?: ReturnType<typeof activeFilters>
      variable: string
      max_cases: number
      dry_run: boolean
    }) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/traffic/cases", {
          params: { path: { project_id: projectId } },
          body,
        }),
      ),
    onSuccess: (_data, vars) => {
      if (!vars.dry_run) {
        void queryClient.invalidateQueries({ queryKey: key(projectId) })
        void queryClient.invalidateQueries({ queryKey: ["projects", projectId, "dataset"] })
      }
    },
  })
}

export { activeFilters }

export function useStats(projectId: string) {
  return useQuery({
    queryKey: key(projectId, "stats"),
    refetchInterval: 15_000,
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/traffic/stats", {
          params: { path: { project_id: projectId } },
        }),
      ),
  })
}

export function useDaily(projectId: string, days: number) {
  return useQuery({
    queryKey: key(projectId, "daily", days),
    refetchInterval: 30_000,
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/traffic/daily", {
          params: { path: { project_id: projectId }, query: { days } },
        }),
      ),
  })
}

export function useConfig(projectId: string) {
  return useQuery({
    queryKey: key(projectId, "config"),
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/traffic/config", {
          params: { path: { project_id: projectId } },
        }),
      ),
  })
}

export function useSaveConfig(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ConfigUpdate) =>
      call(() =>
        api.PUT("/api/v1/projects/{project_id}/traffic/config", {
          params: { path: { project_id: projectId } },
          body,
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: key(projectId) }),
  })
}

export function useRunScoring(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/traffic/scoring/run", {
          params: { path: { project_id: projectId } },
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: key(projectId) }),
  })
}

export function useTokens(projectId: string) {
  return useQuery({
    queryKey: key(projectId, "tokens"),
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/traffic/tokens", {
          params: { path: { project_id: projectId } },
        }),
      ),
  })
}

export function useCreateToken(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (name: string) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/traffic/tokens", {
          params: { path: { project_id: projectId } },
          body: { name },
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: key(projectId, "tokens") }),
  })
}

export function useRevokeToken(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (tokenId: string) =>
      call(() =>
        api.DELETE("/api/v1/projects/{project_id}/traffic/tokens/{token_id}", {
          params: { path: { project_id: projectId, token_id: tokenId } },
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: key(projectId, "tokens") }),
  })
}

export function useChannels(projectId: string) {
  return useQuery({
    queryKey: key(projectId, "channels"),
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/traffic/alerts/channels", {
          params: { path: { project_id: projectId } },
        }),
      ),
  })
}

export function useAddChannel(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ChannelCreate) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/traffic/alerts/channels", {
          params: { path: { project_id: projectId } },
          body,
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: key(projectId, "channels") }),
  })
}

export function useTestChannel(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (channelId: string) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/traffic/alerts/channels/{channel_id}/test", {
          params: { path: { project_id: projectId, channel_id: channelId } },
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: key(projectId, "channels") }),
  })
}

export function useDeleteChannel(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (channelId: string) =>
      call(() =>
        api.DELETE("/api/v1/projects/{project_id}/traffic/alerts/channels/{channel_id}", {
          params: { path: { project_id: projectId, channel_id: channelId } },
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: key(projectId) }),
  })
}

export function useRules(projectId: string) {
  return useQuery({
    queryKey: key(projectId, "rules"),
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/traffic/alerts/rules", {
          params: { path: { project_id: projectId } },
        }),
      ),
  })
}

export function useAddRule(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: RuleCreate) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/traffic/alerts/rules", {
          params: { path: { project_id: projectId } },
          body,
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: key(projectId) }),
  })
}

export function useDeleteRule(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (ruleId: string) =>
      call(() =>
        api.DELETE("/api/v1/projects/{project_id}/traffic/alerts/rules/{rule_id}", {
          params: { path: { project_id: projectId, rule_id: ruleId } },
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: key(projectId) }),
  })
}

export function useAlerts(projectId: string) {
  return useQuery({
    queryKey: key(projectId, "alerts"),
    refetchInterval: 30_000,
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/traffic/alerts", {
          params: { path: { project_id: projectId } },
        }),
      ),
  })
}

export function useResolveAlert(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (alertId: string) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/traffic/alerts/{alert_id}/resolve", {
          params: { path: { project_id: projectId, alert_id: alertId } },
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: key(projectId) }),
  })
}

export function useEvaluateAlerts(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/traffic/alerts/evaluate", {
          params: { path: { project_id: projectId } },
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: key(projectId) }),
  })
}
