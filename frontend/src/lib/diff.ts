/** A line-by-line difference between two prompts (longest common subsequence). No React here. */
export type DiffLine = { kind: "same" | "add" | "remove"; text: string }

/** The text of a prompt as people read it: the system prompt, then the user message. */
export function promptText(version: {
  system_template?: string | null
  user_template?: string | null
}): string {
  const parts: string[] = []
  if (version.system_template) parts.push(`[system]\n${version.system_template}`)
  if (version.user_template) parts.push(`[user]\n${version.user_template}`)
  return parts.join("\n")
}

export function lineDiff(before: string, after: string): DiffLine[] {
  const a = before.split("\n")
  const b = after.split("\n")
  const table: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array<number>(b.length + 1).fill(0),
  )
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--)
      table[i][j] = a[i] === b[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1])
  const out: DiffLine[] = []
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      out.push({ kind: "same", text: a[i] })
      i++
      j++
    } else if (table[i + 1][j] >= table[i][j + 1]) out.push({ kind: "remove", text: a[i++] })
    else out.push({ kind: "add", text: b[j++] })
  }
  while (i < a.length) out.push({ kind: "remove", text: a[i++] })
  while (j < b.length) out.push({ kind: "add", text: b[j++] })
  return out
}

export function diffCounts(lines: DiffLine[]): { added: number; removed: number } {
  return {
    added: lines.filter((l) => l.kind === "add").length,
    removed: lines.filter((l) => l.kind === "remove").length,
  }
}
