/**
 * Your Data hooks: the project's input files (polled while any is still being processed),
 * upload, sheet choice, the golden set's suggested and confirmed column mapping, import,
 * and delete.
 */
"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"
import type { ColumnMapping, InputFileOut, UploadPurpose } from "@/lib/api/types"

const BUSY = new Set(["uploaded", "profiling", "validating", "importing", "extracting"])
const POLL_MS = 1000

function fileParams(projectId: string, fileId: string) {
  return { path: { project_id: projectId, file_id: fileId } }
}

export function isBusy(file: InputFileOut): boolean {
  return BUSY.has(file.status)
}

export function useFiles(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "files"],
    queryFn: async () => {
      const page = await call(() =>
        api.GET("/api/v1/projects/{project_id}/input-files", {
          params: { path: { project_id: projectId }, query: { limit: 100 } },
        }),
      )
      return page.items
    },
    refetchInterval: (query) => ((query.state.data ?? []).some(isBusy) ? POLL_MS : false),
  })
}

function useInvalidate(projectId: string) {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ["projects", projectId] })
}

export function useUpload(projectId: string) {
  const invalidate = useInvalidate(projectId)
  return useMutation({
    mutationFn: ({ file, purpose }: { file: File; purpose: UploadPurpose }) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/input-files", {
          params: { path: { project_id: projectId } },
          body: { file: file as unknown as string, purpose },
          bodySerializer: (body) => {
            const form = new FormData()
            form.append("file", body.file as unknown as File)
            form.append("purpose", body.purpose)
            return form
          },
        }),
      ),
    onSettled: invalidate,
  })
}

export function useSelectSheet(projectId: string) {
  const invalidate = useInvalidate(projectId)
  return useMutation({
    mutationFn: ({ fileId, sheet }: { fileId: string; sheet: string }) =>
      call(() =>
        api.PUT("/api/v1/projects/{project_id}/input-files/{file_id}/sheet", {
          params: fileParams(projectId, fileId),
          body: { sheet },
        }),
      ),
    onSettled: invalidate,
  })
}

export function useMappingSuggestion(projectId: string, fileId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["projects", projectId, "files", fileId, "suggestion"],
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/input-files/{file_id}/mapping-suggestion", {
          params: fileParams(projectId, fileId),
        }),
      ),
    enabled,
  })
}

export function useSubmitMapping(projectId: string) {
  const invalidate = useInvalidate(projectId)
  return useMutation({
    mutationFn: ({ fileId, mapping }: { fileId: string; mapping: ColumnMapping }) =>
      call(() =>
        api.PUT("/api/v1/projects/{project_id}/input-files/{file_id}/mapping", {
          params: fileParams(projectId, fileId),
          body: { mapping },
        }),
      ),
    onSettled: invalidate,
  })
}

/** A table of inputs: which column fills each prompt variable. The file is read again, one test case per row. */
export function useSetVariables(projectId: string) {
  const invalidate = useInvalidate(projectId)
  return useMutation({
    mutationFn: ({
      fileId,
      variables,
      expectedOutput,
      category,
    }: {
      fileId: string
      variables: Record<string, string>
      expectedOutput: string | null
      category: string | null
    }) =>
      call(() =>
        api.PUT("/api/v1/projects/{project_id}/input-files/{file_id}/variables", {
          params: fileParams(projectId, fileId),
          body: { variables, expected_output: expectedOutput, category },
        }),
      ),
    onSettled: invalidate,
  })
}

export function useImport(projectId: string) {
  const invalidate = useInvalidate(projectId)
  return useMutation({
    mutationFn: (fileId: string) =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/input-files/{file_id}/import", {
          params: fileParams(projectId, fileId),
        }),
      ),
    onSettled: invalidate,
  })
}

export function useDeleteFile(projectId: string) {
  const invalidate = useInvalidate(projectId)
  return useMutation({
    mutationFn: (fileId: string) =>
      call(() =>
        api.DELETE("/api/v1/projects/{project_id}/input-files/{file_id}", {
          params: fileParams(projectId, fileId),
        }),
      ),
    onSettled: invalidate,
  })
}
