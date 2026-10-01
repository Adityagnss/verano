/**
 * The whole guide as one piece of Markdown for the clipboard. Pictures cannot be copied as
 * text, so each one becomes a line describing it, placed under the heading it illustrates.
 */
import { slug } from "@/components/common/markdown"

export function pageAsMarkdown(source: string, diagramLabels: Record<string, string>): string {
  const out: string[] = []
  let fenced = false
  for (const line of source.split("\n")) {
    out.push(line)
    if (line.startsWith("```")) fenced = !fenced
    const heading = !fenced && /^#{2,3} (.*)$/.exec(line)
    const label = heading ? diagramLabels[slug(heading[1])] : undefined
    if (label) out.push("", `*Diagram: ${label}.*`)
  }
  return out.join("\n")
}
