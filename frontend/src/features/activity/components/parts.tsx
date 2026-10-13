/** Small building blocks shared by the Activity tabs: a panel, a headline number, a ranked list. */
"use client"

import { ArrowDownRight, ArrowUpRight, Minus, Sparkles } from "lucide-react"
import type { ReactNode } from "react"

import { formatCost, formatTokens } from "@/lib/format"
import { cn } from "@/lib/utils"

import type { Change, Metric } from "../domain"
import { Sparkline } from "./charts"

export function formatMetric(metric: Metric, value: number): string {
  if (metric === "spend") return formatCost(value)
  if (metric === "tokens") return value ? formatTokens(value) : "0"
  return value.toLocaleString("en-US")
}

export function Panel({
  title,
  action,
  children,
  className,
}: {
  title: string
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section
      className={cn("bg-card border-border flex min-w-0 flex-col gap-4 rounded-xl border p-5", className)}
    >
      <header className="flex items-center justify-between gap-3">
        <h3 className="text-[0.95rem] font-semibold">{title}</h3>
        {action}
      </header>
      {children}
    </section>
  )
}

export function LinkButton({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-lagoon-strong hover:text-foreground focus-visible:ring-ring/50 rounded text-sm font-medium underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:outline-none"
    >
      {children}
    </button>
  )
}

export function ChangeLine({ change, period }: { change: Change; period: string }) {
  if (change.kind === "none") return null
  if (change.kind === "new") {
    return (
      <span className="text-text-secondary inline-flex items-center gap-1">
        <Sparkles className="size-3.5" aria-hidden /> New: nothing in the {period} before
      </span>
    )
  }
  if (change.kind === "gone")
    return <span className="text-text-secondary">None now, some in the {period} before</span>
  const Icon = change.value > 0.005 ? ArrowUpRight : change.value < -0.005 ? ArrowDownRight : Minus
  const words =
    change.value >= 1
      ? `${(1 + change.value).toFixed(1).replace(/\.0$/, "")}× as much as`
      : change.value > 0.005
        ? `${Math.round(change.value * 100)}% more than`
        : change.value < -0.005
          ? `${Math.round(-change.value * 100)}% less than`
          : "About the same as"
  return (
    <span className="text-text-secondary inline-flex items-center gap-1">
      <Icon className="size-3.5" aria-hidden />
      {words} the {period} before
    </span>
  )
}

export function Headline({
  label,
  value,
  detail,
  change,
  period,
  line,
}: {
  label: string
  value: string
  detail?: ReactNode
  change: Change
  period: string
  line?: number[]
}) {
  return (
    <div className="bg-card border-border flex min-w-0 flex-col gap-1.5 rounded-xl border px-5 py-4">
      <div className="flex items-start justify-between gap-3">
        <span className="text-text-secondary text-sm">{label}</span>
        {line ? <Sparkline values={line} label={`${label} per day`} /> : null}
      </div>
      <span className="text-[1.6rem] leading-none font-semibold [font-stretch:87.5%] tabular-nums">
        {value}
      </span>
      {detail ? <span className="text-text-secondary text-xs">{detail}</span> : null}
      <span className="text-xs">
        <ChangeLine change={change} period={period} />
      </span>
    </div>
  )
}

export function RankedList({
  items,
  empty,
}: {
  items: { id: string; name: string; detail?: string; color?: string; values: string[] }[]
  empty: string
}) {
  if (!items.length) return <p className="text-text-muted py-6 text-center text-sm">{empty}</p>
  return (
    <ol className="flex flex-col">
      {items.map((item, index) => (
        <li key={item.id} className="border-border flex items-center gap-3 border-t py-2.5 first:border-t-0">
          <span className="text-text-muted w-4 text-right text-sm tabular-nums">{index + 1}</span>
          {item.color ? (
            <span aria-hidden className="size-2.5 shrink-0 rounded-full" style={{ background: item.color }} />
          ) : null}
          <span className="flex min-w-0 flex-1 flex-col">
            <span className="truncate text-sm font-medium">{item.name}</span>
            {item.detail ? <span className="text-text-muted truncate text-xs">{item.detail}</span> : null}
          </span>
          {item.values.map((v, i) => (
            <span
              key={i}
              className={cn(
                "text-sm tabular-nums",
                i === 0 ? "font-medium" : "text-text-secondary w-20 text-right",
              )}
            >
              {v}
            </span>
          ))}
        </li>
      ))}
    </ol>
  )
}
