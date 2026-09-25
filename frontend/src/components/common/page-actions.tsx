/**
 * Holds a screen's single primary action, always in the same place: bottom right
 * (DEVELOPMENT.md C1). Optional secondary content (a summary line) sits to its left.
 */
import type { ReactNode } from "react"

export function PageActions({ summary, children }: { summary?: ReactNode; children: ReactNode }) {
  return (
    <div className="border-border bg-background/95 sticky bottom-0 mt-8 flex items-center justify-end gap-4 border-t py-4 backdrop-blur">
      {summary ? <div className="text-muted-foreground mr-auto text-sm">{summary}</div> : null}
      {children}
    </div>
  )
}
