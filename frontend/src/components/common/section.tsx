/**
 * One part of a step, on a white bordered panel: an optional position in the step's order,
 * a title, one line on what it's for, an optional state badge and action on the right, then
 * its content. Numbers are shown only where the parts really are done in order.
 */
import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

export function Section({
  number,
  title,
  description,
  badge,
  action,
  children,
  className,
  muted = false,
}: {
  number?: number
  title: string
  description?: string
  badge?: ReactNode
  action?: ReactNode
  children?: ReactNode
  className?: string
  muted?: boolean
}) {
  return (
    <section
      className={cn(
        "bg-card border-border flex flex-col gap-5 rounded-xl border px-4 py-4 shadow-[0_1px_2px_rgb(20_32_58/0.04)] sm:px-6 sm:py-5",
        muted && "opacity-55",
        className,
      )}
    >
      <div className="flex flex-wrap items-start gap-3">
        {number !== undefined ? (
          <span className="border-border-strong text-text-secondary mt-px flex size-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold tabular-nums">
            {number}
          </span>
        ) : null}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[1.05rem] font-semibold">{title}</h3>
            {badge}
          </div>
          {description ? <p className="text-text-secondary mt-0.5 text-sm">{description}</p> : null}
        </div>
        {action ? <div className="flex shrink-0 flex-wrap items-center gap-3">{action}</div> : null}
      </div>
      {children}
    </section>
  )
}
