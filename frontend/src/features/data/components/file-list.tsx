/**
 * The project's files with their status. A golden set that has been read shows its sheet
 * choice (XLSX with several sheets) and its column mapping; input files and documents are
 * ready as soon as they are read.
 */
"use client"

import { Loader2, Trash2 } from "lucide-react"

import { EmptyState } from "@/components/common/empty-state"
import { StatusBadge, type Tone } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/select"
import type { InputFileOut } from "@/lib/api/types"

import { DATA_COPY } from "../copy"
import { isBusy, useDeleteFile, useSelectSheet } from "../hooks"
import { MappingPanel, Report } from "./mapping-panel"

const MAPPABLE = new Set(["ready", "validated", "imported"])
const DONE = new Set(["imported", "extracted"])
const ACTION = new Set(["ready", "validated"])

function statusTone(file: InputFileOut): Tone {
  if (file.status === "failed") return "danger"
  if (DONE.has(file.status)) return "success"
  if (ACTION.has(file.status)) return "brand"
  return "info"
}

function Detail({ file }: { file: InputFileOut }) {
  const parts = [DATA_COPY.kind[file.kind]]
  if (file.row_count !== null) parts.push(DATA_COPY.rows(file.row_count))
  if (file.section_count !== null) parts.push(DATA_COPY.sections(file.section_count))
  if (file.imported_rows !== null) parts.push(DATA_COPY.imported(file.imported_rows))
  return <>{parts.join(" · ")}</>
}

function FileCard({ projectId, file }: { projectId: string; file: InputFileOut }) {
  const remove = useDeleteFile(projectId)
  const sheet = useSelectSheet(projectId)
  const sheets = file.profile?.sheets ?? []
  const rows = file.kind === "golden_set"
  const warnings = rows ? [] : (file.profile?.warnings ?? [])
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="truncate">{file.filename}</span>
          <StatusBadge
            tone={statusTone(file)}
            icon={isBusy(file) ? <Loader2 className="animate-spin" /> : null}
          >
            {DATA_COPY.status[file.status]}
          </StatusBadge>
        </CardTitle>
        <CardDescription>
          <Detail file={file} />
        </CardDescription>
        <CardAction>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={DATA_COPY.remove}
            onClick={() => remove.mutate(file.id)}
          >
            <Trash2 />
          </Button>
        </CardAction>
      </CardHeader>
      {file.error_message || warnings.length || (rows && (MAPPABLE.has(file.status) || sheets.length > 1)) ? (
        <CardContent className="flex flex-col gap-4">
          {file.error_message ? <p className="text-danger-strong text-sm">{file.error_message}</p> : null}
          {warnings.map((warning) => (
            <p key={warning} className="bg-marigold-soft text-marigold-strong rounded-lg p-3 text-sm">
              {warning}
            </p>
          ))}
          {rows && sheets.length > 1 ? (
            <div className="flex max-w-xs flex-col gap-1.5">
              <Label htmlFor={`${file.id}-sheet`}>{DATA_COPY.sheet}</Label>
              <NativeSelect
                id={`${file.id}-sheet`}
                value={file.profile?.sheet ?? ""}
                onChange={(event) => sheet.mutate({ fileId: file.id, sheet: event.target.value })}
              >
                {sheets.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </NativeSelect>
            </div>
          ) : null}
          {rows && file.status === "imported" && file.validation_report ? (
            <Report report={file.validation_report} />
          ) : null}
          {rows && (file.status === "ready" || file.status === "validated") ? (
            <MappingPanel projectId={projectId} file={file} />
          ) : null}
        </CardContent>
      ) : null}
    </Card>
  )
}

export function FileList({ projectId, files }: { projectId: string; files: InputFileOut[] }) {
  if (files.length === 0) return <EmptyState title={DATA_COPY.filesHeading} description={DATA_COPY.noFiles} />
  return (
    <div className="flex flex-col gap-3">
      {files.map((file) => (
        <FileCard key={file.id} projectId={projectId} file={file} />
      ))}
    </div>
  )
}
