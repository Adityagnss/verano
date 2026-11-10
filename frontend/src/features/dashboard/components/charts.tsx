/**
 * The dashboard's charts, drawn in plain HTML and SVG. Every model keeps the same color in
 * every chart (assigned by name, never by rank); the first four models get the validated
 * categorical colors and any further model is neutral grey. Each chart has a legend or
 * direct labels and a text value, so color is never the only carrier of identity. Bars are
 * separate small charts per measure (never two scales on one axis).
 */
"use client"

import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts"

import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"

import type { Trend } from "../domain"
import { pct } from "../domain"

const SLOTS = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)"]

export function colorOf(models: string[], model: string): string {
  const index = [...models].sort().indexOf(model)
  return index >= 0 && index < SLOTS.length ? SLOTS[index] : "var(--series-other)"
}

export function ModelBars({
  title,
  hint,
  rows,
  format,
}: {
  title: string
  hint: string
  rows: { model: string; color: string; value: number | null }[]
  format: (value: number) => string
}) {
  const max = Math.max(...rows.map((r) => r.value ?? 0), 0) || 1
  return (
    <figure className="flex flex-col gap-3" aria-label={title}>
      <figcaption>
        <h4 className="text-sm font-semibold">{title}</h4>
        <p className="text-text-muted text-xs">{hint}</p>
      </figcaption>
      <ul className="flex flex-col gap-2.5">
        {rows.map((row) => (
          <li key={row.model} className="flex flex-col gap-1">
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="flex min-w-0 items-center gap-2">
                <span
                  aria-hidden
                  className="size-2.5 shrink-0 rounded-sm"
                  style={{ background: row.color }}
                />
                <span className="truncate">{row.model}</span>
              </span>
              <span className="font-medium tabular-nums">
                {row.value === null ? "unknown" : format(row.value)}
              </span>
            </div>
            <div className="bg-chart-track h-2 overflow-hidden rounded-full" role="presentation">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${row.value === null ? 0 : Math.max(2, (row.value / max) * 100)}%`,
                  background: row.color,
                }}
              />
            </div>
          </li>
        ))}
      </ul>
    </figure>
  )
}

export function TrendChart({ trends, models }: { trends: Trend[]; models: string[] }) {
  const labels = trends[0]?.points ?? []
  const config: ChartConfig = Object.fromEntries(
    trends.map((t, i) => [`m${i}`, { label: t.model, color: colorOf(models, t.model) }]),
  )
  const data = labels.map((point, index) => ({
    label: point.label,
    ...Object.fromEntries(trends.map((t, i) => [`m${i}`, t.points[index]?.value ?? null])),
  }))
  return (
    <figure className="flex flex-col gap-3" aria-label="Pass rate by experiment">
      <ChartContainer config={config} className="aspect-[4/3] w-full sm:aspect-video">
        <LineChart data={data} margin={{ left: 0, right: 12, top: 8 }}>
          <CartesianGrid vertical={false} />
          <XAxis dataKey="label" tickLine={false} axisLine={false} tickMargin={8} />
          <YAxis
            domain={[0, 1]}
            ticks={[0, 0.5, 1]}
            tickFormatter={(v: number) => pct(v)}
            tickLine={false}
            axisLine={false}
            width={44}
          />
          <ChartTooltip
            content={
              <ChartTooltipContent formatter={(value) => pct(typeof value === "number" ? value : null)} />
            }
          />
          <ChartLegend content={<ChartLegendContent />} />
          {trends.map((t, i) => (
            <Line
              key={t.model}
              dataKey={`m${i}`}
              type="monotone"
              stroke={`var(--color-m${i})`}
              strokeWidth={2}
              dot={{ r: 4 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ChartContainer>
      <details className="text-sm">
        <summary className="text-lagoon-strong cursor-pointer font-medium">Show as a table</summary>
        <div className="overflow-x-auto pt-2">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="text-text-secondary">
                <th className="py-1 pr-4 font-medium">Experiment</th>
                {trends.map((t) => (
                  <th key={t.model} className="py-1 pr-4 font-medium">
                    {t.model}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {labels.map((point, index) => (
                <tr key={index} className="border-border border-t">
                  <td className="py-1 pr-4">
                    {point.label}
                    {point.date ? ` · ${new Date(point.date).toLocaleDateString()}` : ""}
                  </td>
                  {trends.map((t) => (
                    <td key={t.model} className="py-1 pr-4 tabular-nums">
                      {t.points[index].value === null ? "—" : pct(t.points[index].value ?? 0)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  )
}

export function SpendBar({
  parts,
  format,
}: {
  parts: { key: string; label: string; cost: number; calls: number }[]
  format: (v: number) => string
}) {
  const total = parts.reduce((sum, part) => sum + part.cost, 0)
  return (
    <figure className="flex flex-col gap-3" aria-label="Where the money went">
      <div className="flex h-3 gap-0.5 overflow-hidden rounded-full" role="presentation">
        {parts.map((part, index) => (
          <div
            key={part.key}
            title={`${part.label}: ${format(part.cost)}`}
            className="h-full first:rounded-l-full last:rounded-r-full"
            style={{
              width: `${total ? Math.max(2, (part.cost / total) * 100) : 100 / parts.length}%`,
              background: SLOTS[index] ?? "var(--series-other)",
            }}
          />
        ))}
      </div>
      <ul className="flex flex-col gap-1.5 text-sm">
        {parts.map((part, index) => (
          <li key={part.key} className="flex items-baseline justify-between gap-3">
            <span className="flex items-center gap-2">
              <span
                aria-hidden
                className="size-2.5 rounded-sm"
                style={{ background: SLOTS[index] ?? "var(--series-other)" }}
              />
              {part.label}
              <span className="text-text-muted text-xs">
                {part.calls.toLocaleString()} {part.calls === 1 ? "call" : "calls"}
              </span>
            </span>
            <span className="font-medium tabular-nums">{format(part.cost)}</span>
          </li>
        ))}
      </ul>
    </figure>
  )
}
