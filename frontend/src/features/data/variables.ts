/** Pure rules for mapping table columns to prompt variables. No React here. */
import type { InputFileOut } from "@/lib/api/types"

/** Which column fills each variable: a column with the same name (ignoring case and separators) is pre-picked. */
export function suggestVariables(variables: string[], columns: string[]): Record<string, string> {
  const norm = (text: string) => text.toLowerCase().replace(/[^a-z0-9]/g, "")
  const out: Record<string, string> = {}
  for (const name of variables) {
    const match = columns.find((c) => norm(c) === norm(name))
    if (match) out[name] = match
  }
  return out
}

/** What is wrong with the choices, in words, before anything is sent. */
export function variableProblems(variables: string[], chosen: Record<string, string>): string[] {
  const missing = variables.filter((v) => !chosen[v])
  const problems = missing.map((v) => `Pick the column that fills {{${v}}}.`)
  if (variables.length === 0)
    problems.push("The prompt has no variables to fill. Add one like {{message}} first.")
  return problems
}

const LEFT_OUT = /^Row \d+ was left out/

/** The "Row N was left out: x is empty in it." lines the import left in the file's warnings. */
export function leftOutRows(file: InputFileOut): string[] {
  return (file.profile?.warnings ?? []).filter((w) => LEFT_OUT.test(w))
}

/** Warnings that are not about left-out rows. */
export function otherWarnings(file: InputFileOut): string[] {
  return (file.profile?.warnings ?? []).filter((w) => !LEFT_OUT.test(w))
}

/** Is this file a table whose columns can fill prompt variables? */
export function isTableInput(file: InputFileOut): boolean {
  return (
    file.kind === "raw_inputs" &&
    (file.profile?.columns.length ?? 0) > 0 &&
    !["txt", "md"].includes(String(file.format))
  )
}

/** The variables an earlier mapping used, when the file was mapped before. */
export function savedVariables(file: InputFileOut): Record<string, string> {
  const mapping = file.column_mapping as { variables?: Record<string, string> } | null
  return mapping?.variables ?? {}
}
