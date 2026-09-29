/**
 * Golden-set mapping: which column holds the correct answer, the grading criteria, the
 * category, tags and the input file an entry belongs to. All are optional: with no answer
 * column, each row is itself the expected answer. "Check entries" produces the report with
 * row numbers, and "Import" writes the answers onto the input files.
 */
"use client"

import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/select"
import type { ColumnMapping, InputFileOut, ValidationReport } from "@/lib/api/types"

import { DATA_COPY } from "../copy"
import { useImport, useMappingSuggestion, useSubmitMapping } from "../hooks"

const TARGETS = ["expected_output", "rubric", "category", "tags", "input_file"] as const

function ColumnSelect({
  id,
  label,
  columns,
  value,
  onChange,
}: {
  id: string
  label: string
  columns: string[]
  value: string | null | undefined
  onChange: (value: string | null) => void
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <NativeSelect id={id} value={value ?? ""} onChange={(event) => onChange(event.target.value || null)}>
        <option value="">{DATA_COPY.none}</option>
        {columns.map((column) => (
          <option key={column} value={column}>
            {column}
          </option>
        ))}
      </NativeSelect>
    </div>
  )
}

export function Report({ report }: { report: ValidationReport }) {
  return (
    <div className="bg-subtle ring-border flex flex-col gap-2 rounded-lg p-3 text-sm ring-1">
      <p className="font-medium">{DATA_COPY.report(report.valid_rows, report.skipped_rows)}</p>
      {report.issues.length ? (
        <ul className="text-muted-foreground flex flex-col gap-1">
          {report.issues.map((issue) => (
            <li key={`${issue.kind}-${issue.field ?? ""}`}>
              <span className="text-warning-strong">{issue.message}</span> (
              {DATA_COPY.rowsList(issue.rows, issue.count)})
            </li>
          ))}
        </ul>
      ) : null}
      {report.warnings.map((warning) => (
        <p key={warning} className="text-warning-strong">
          {warning}
        </p>
      ))}
    </div>
  )
}

type Props = { projectId: string; file: InputFileOut }

export function MappingPanel({ projectId, file }: Props) {
  const suggestion = useMappingSuggestion(projectId, file.id, true)
  const submit = useSubmitMapping(projectId)
  const importRows = useImport(projectId)
  const [edited, setMapping] = useState<ColumnMapping | null>(null)
  const mapping = edited ?? file.column_mapping ?? suggestion.data?.mapping ?? null

  if (!suggestion.data || !mapping) return <ErrorMessage error={suggestion.error} />
  const columns = file.profile?.columns ?? []
  const report = file.status === "validated" ? file.validation_report : null
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h4 className="text-sm font-medium">{DATA_COPY.mappingHeading}</h4>
        <p className="text-muted-foreground text-xs">{DATA_COPY.mappingHint}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {TARGETS.map((target) => (
          <ColumnSelect
            key={target}
            id={`${file.id}-${target}`}
            label={DATA_COPY.targets[target]}
            columns={columns}
            value={mapping[target]}
            onChange={(column) => setMapping({ ...mapping, [target]: column })}
          />
        ))}
      </div>
      <ErrorMessage error={submit.error ?? importRows.error} />
      {report ? <Report report={report} /> : null}
      <div className="flex gap-2">
        <Button
          variant={report ? "outline" : "default"}
          disabled={submit.isPending}
          onClick={() => void submit.mutateAsync({ fileId: file.id, mapping }).catch(() => undefined)}
        >
          {submit.isPending ? DATA_COPY.checking : DATA_COPY.check}
        </Button>
        {report && report.valid_rows > 0 ? (
          <Button
            disabled={importRows.isPending}
            onClick={() => void importRows.mutateAsync(file.id).catch(() => undefined)}
          >
            {DATA_COPY.importRows(report.valid_rows)}
          </Button>
        ) : null}
      </div>
    </div>
  )
}
