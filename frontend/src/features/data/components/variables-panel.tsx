/**
 * Column mapping for a table of inputs: which column fills each variable of the prompt. Saving reads the file again
 * with every row as a test case that carries all its variables; a row with an empty mapped cell is left out and
 * listed here with its row number.
 */
"use client"

import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { useCurrentPrompt } from "@/features/prompt/hooks"
import type { InputFileOut } from "@/lib/api/types"

import { useSetVariables } from "../hooks"
import { leftOutRows, otherWarnings, savedVariables, suggestVariables, variableProblems } from "../variables"

const VARIABLES_COPY = {
  heading: "Fill the prompt from your columns",
  hint: "Each row of this table becomes one test case. Say which column goes into each variable of your prompt. A row with an empty cell in a chosen column is left out, never sent half empty.",
  choose: "Choose a column",
  none: "None",
  expected: "Column with the correct answer (optional)",
  category: "Column with the kind of case (optional)",
  save: "Use these columns",
  saving: "Reading the rows…",
  noPrompt: "Save a prompt first. Its variables, like {{message}}, are what the columns fill.",
  noVariables:
    "Your prompt has no variables yet. Add one like {{message}} on the Prompt step, then map it here.",
  used: (rows: number | null) => `${rows ?? 0} test cases made from this table.`,
  leftOut: (n: number) => `${n} row${n === 1 ? " was" : "s were"} left out`,
  more: "Fix the empty cells in your file, or pick other columns, and use the columns again.",
}

export function VariablesPanel({ projectId, file }: { projectId: string; file: InputFileOut }) {
  const prompt = useCurrentPrompt(projectId)
  const save = useSetVariables(projectId)
  const columns = file.profile?.columns ?? []
  const variables = prompt.data?.latest_version.variables ?? []
  const [edited, setEdited] = useState<Record<string, string> | null>(null)
  const [expected, setExpected] = useState("")
  const [category, setCategory] = useState("")
  const chosen = edited ?? { ...suggestVariables(variables, columns), ...savedVariables(file) }
  const problems = variableProblems(variables, chosen)
  const busy = save.isPending || file.status === "importing"
  const left = leftOutRows(file)
  const warnings = otherWarnings(file)

  if (prompt.isPending) return <Skeleton className="h-24" aria-label="Loading your prompt" />
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h4 className="text-sm font-medium">{VARIABLES_COPY.heading}</h4>
        <p className="text-muted-foreground text-xs">{VARIABLES_COPY.hint}</p>
      </div>
      {prompt.data === null ? <p className="text-warning-strong text-sm">{VARIABLES_COPY.noPrompt}</p> : null}
      {prompt.data && variables.length === 0 ? (
        <p className="text-warning-strong text-sm">{VARIABLES_COPY.noVariables}</p>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {variables.map((name) => (
          <div key={name} className="flex flex-col gap-1.5">
            <Label htmlFor={`${file.id}-var-${name}`}>{`{{${name}}}`}</Label>
            <NativeSelect
              id={`${file.id}-var-${name}`}
              value={chosen[name] ?? ""}
              onChange={(e) => setEdited({ ...chosen, [name]: e.target.value })}
            >
              <option value="">{VARIABLES_COPY.choose}</option>
              {columns.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </NativeSelect>
          </div>
        ))}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${file.id}-var-expected`}>{VARIABLES_COPY.expected}</Label>
          <NativeSelect
            id={`${file.id}-var-expected`}
            value={expected}
            onChange={(e) => setExpected(e.target.value)}
          >
            <option value="">{VARIABLES_COPY.none}</option>
            {columns.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${file.id}-var-category`}>{VARIABLES_COPY.category}</Label>
          <NativeSelect
            id={`${file.id}-var-category`}
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="">{VARIABLES_COPY.none}</option>
            {columns.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </NativeSelect>
        </div>
      </div>
      {problems.length && edited ? (
        <ul className="text-danger-strong list-disc pl-5 text-sm" role="alert">
          {problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      ) : null}
      <ErrorMessage error={save.error} />
      {file.status === "imported" ? (
        <div
          className="bg-subtle ring-border flex flex-col gap-2 rounded-lg p-3 text-sm ring-1"
          role="status"
        >
          <p className="font-medium">{VARIABLES_COPY.used(file.imported_rows)}</p>
          {left.length ? (
            <>
              <p className="text-warning-strong font-medium">{VARIABLES_COPY.leftOut(left.length)}</p>
              <ul className="text-warning-strong flex flex-col gap-0.5">
                {left.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
              <p className="text-text-muted text-xs">{VARIABLES_COPY.more}</p>
            </>
          ) : null}
        </div>
      ) : null}
      {warnings.map((w) => (
        <p key={w} className="bg-marigold-soft text-marigold-strong rounded-lg p-3 text-sm">
          {w}
        </p>
      ))}
      <Button
        className="self-start"
        disabled={busy || problems.length > 0}
        onClick={() =>
          void save
            .mutateAsync({
              fileId: file.id,
              variables: Object.fromEntries(variables.map((v) => [v, chosen[v]])),
              expectedOutput: expected || null,
              category: category || null,
            })
            .catch(() => undefined)
        }
      >
        {busy ? VARIABLES_COPY.saving : VARIABLES_COPY.save}
      </Button>
    </div>
  )
}
