/** Pure rules for the Prompt step: a name and a "what changed" note made from the prompt itself. No React here. */
import { diffCounts, lineDiff, promptText } from "@/lib/diff"

const MAX_NAME = 60

/** A prompt's name taken from its first line (markdown marks and a leading "You are" removed). */
export function promptName(system: string, user: string): string {
  const line = `${system}\n${user}`
    .split("\n")
    .map((l) => l.replace(/^[#>*\-\s]+/, "").trim())
    .find((l) => l.length > 0)
  if (!line) return "My prompt"
  return line.length > MAX_NAME ? `${line.slice(0, MAX_NAME - 1).trimEnd()}…` : line
}

type Templates = { system_template?: string | null; user_template?: string | null }

/** "Edited: +3 −1 lines": the note a new version gets when its author did not write one. */
export function autoReason(before: Templates, after: Templates): string {
  const { added, removed } = diffCounts(lineDiff(promptText(before), promptText(after)))
  if (added === 0 && removed === 0) return "Settings changed"
  return `Edited: +${added} −${removed} lines`
}
