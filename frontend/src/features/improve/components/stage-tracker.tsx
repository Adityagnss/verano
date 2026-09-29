/** The four stages of an improvement session, with the finished ones checked and the current one marked. */
import { Check, Loader2 } from "lucide-react"

import { cn } from "@/lib/utils"

import { IMPROVE_COPY } from "../copy"

const ORDER = ["analyzing", "testing", "confirming", "done"]

export function StageTracker({ stage }: { stage: string }) {
  const failed = stage === "failed"
  const current = failed ? -1 : ORDER.indexOf(stage)
  return (
    <ol className="grid gap-2 sm:grid-cols-4">
      {IMPROVE_COPY.tracker.map((label, index) => {
        const done = !failed && (index < current || stage === "done")
        const active = !failed && index === current && stage !== "done"
        return (
          <li
            key={label}
            className={cn(
              "bg-card ring-border flex items-center gap-2.5 rounded-lg p-3 text-sm ring-1",
              active && "ring-marigold bg-marigold-soft/50",
            )}
          >
            <span
              className={cn(
                "flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ring-1",
                done
                  ? "bg-success-soft text-success-strong ring-success/30"
                  : active
                    ? "bg-marigold ring-marigold text-white"
                    : "bg-card text-text-muted ring-border-strong",
              )}
            >
              {done ? (
                <Check className="size-3.5" />
              ) : active ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                index + 1
              )}
            </span>
            <span className={cn(done || active ? "text-foreground" : "text-text-muted")}>{label}</span>
          </li>
        )
      })}
    </ol>
  )
}
