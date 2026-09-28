/**
 * A headline number: a label, the value, and one line of context (which model it belongs
 * to). `winner` marks the tile that answers "which is best", in the one accent color.
 */
import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

export function StatTile({
  label,
  value,
  detail,
  winner = false,
}: {
  label: string
  value: ReactNode
  detail?: ReactNode
  winner?: boolean
}) {
  return (
    <div
      className={cn(
        "bg-card border-border flex flex-col gap-1 rounded-xl border px-5 py-4",
        winner && "border-marigold/60 bg-marigold-soft/50",
      )}
    >
      <span className="text-text-secondary text-sm">{label}</span>
      <span className="text-[1.6rem] leading-tight font-semibold [font-stretch:87.5%] tabular-nums">
        {value}
      </span>
      {detail ? <span className="text-text-secondary truncate text-sm">{detail}</span> : null}
    </div>
  )
}
