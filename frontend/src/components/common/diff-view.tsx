/** A prompt difference: changed lines with one line of context either side, unchanged stretches folded. */
import { type DiffLine } from "@/lib/diff"
import { cn } from "@/lib/utils"

export function DiffView({ lines }: { lines: DiffLine[] }) {
  const near = lines.map((_, i) =>
    [i - 1, i, i + 1].some((k) => k >= 0 && k < lines.length && lines[k].kind !== "same"),
  )
  const shown: { line: DiffLine; gapBefore: boolean }[] = []
  lines.forEach((line, i) => {
    if (near[i]) shown.push({ line, gapBefore: i > 0 && !near[i - 1] })
  })
  if (shown.length === 0) return <p className="text-text-muted text-xs">No difference.</p>
  return (
    <pre className="bg-card ring-border max-h-72 overflow-auto rounded-lg p-2 font-mono text-xs whitespace-pre-wrap ring-1">
      {shown.map(({ line, gapBefore }, index) => (
        <div key={index}>
          {gapBefore ? <div className="text-text-muted">…</div> : null}
          <div
            className={cn(
              line.kind === "add" && "text-success",
              line.kind === "remove" && "text-destructive",
              line.kind === "same" && "text-muted-foreground",
            )}
          >
            {line.kind === "add" ? "+ " : line.kind === "remove" ? "- " : "  "}
            {line.text || " "}
          </div>
        </div>
      ))}
    </pre>
  )
}
