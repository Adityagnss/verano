/**
 * Holds a screen's single primary action, always in the same place: bottom right
 * (DEVELOPMENT.md C1). Optional secondary content (a summary line) sits to its left.
 */
import type { ReactNode } from "react"

export function PageActions({ summary, children }: { summary?: ReactNode; children: ReactNode }) {
  return (
    <div className="bg-card/95 ring-border shadow-float sticky bottom-4 z-10 mt-8 flex items-center justify-end gap-4 rounded-xl px-5 py-3 ring-1 backdrop-blur">
      {summary ? <div className="text-text-secondary mr-auto text-sm">{summary}</div> : null}
      {children}
    </div>
  )
}
