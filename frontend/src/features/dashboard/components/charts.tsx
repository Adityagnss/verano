/**
 * The dashboard's charts, drawn in plain HTML and SVG. Every model keeps the same color in
 * every chart (assigned by name, never by rank); the first four models get the validated
 * categorical colors and any further model is neutral grey. Each chart has a legend or
 * direct labels and a text value, so color is never the only carrier of identity. Bars are
 * separate small charts per measure (never two scales on one axis).
 */
"use client"

import { useState } from "react"

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

const W = 640
const H = 240
const PAD = { left: 40, right: 16, top: 12, bottom: 30 }

export function TrendChart({ trends, models }: { trends: Trend[]; models: string[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const count = trends[0]?.points.length ?? 0
  const x = (index: number) =>
    PAD.left +
    (count <= 1 ? (W - PAD.left - PAD.right) / 2 : (index / (count - 1)) * (W - PAD.left - PAD.right))
  const y = (value: number) => PAD.top + (1 - value) * (H - PAD.top - PAD.bottom)
  const labels = trends[0]?.points ?? []
  return (
    <figure className="flex flex-col gap-3" aria-label="Pass rate by experiment">
      <ul className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
        {trends.map((trend) => (
          <li key={trend.model} className="flex items-center gap-2">
            <span
              aria-hidden
              className="h-0.5 w-4 rounded"
              style={{ background: colorOf(models, trend.model) }}
            />
            {trend.model}
          </li>
        ))}
      </ul>
      <div className="relative">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full"
          role="img"
          aria-label="Line chart of each model's pass rate across experiments, oldest to newest"
          onMouseLeave={() => setHover(null)}
          onMouseMove={(event) => {
            const box = event.currentTarget.getBoundingClientRect()
            const at = ((event.clientX - box.left) / box.width) * W
            const nearest = Math.round(((at - PAD.left) / (W - PAD.left - PAD.right)) * (count - 1))
            setHover(count === 0 ? null : Math.min(count - 1, Math.max(0, nearest)))
          }}
        >
          {[0, 0.25, 0.5, 0.75, 1].map((tick) => (
            <g key={tick}>
              <line
                x1={PAD.left}
                x2={W - PAD.right}
                y1={y(tick)}
                y2={y(tick)}
                stroke="var(--border-color)"
                strokeWidth={1}
              />
              <text x={PAD.left - 8} y={y(tick) + 4} textAnchor="end" fontSize={11} fill="var(--text-muted)">
                {pct(tick)}
              </text>
            </g>
          ))}
          {labels.map((point, index) => (
            <text
              key={index}
              x={x(index)}
              y={H - 8}
              textAnchor="middle"
              fontSize={11}
              fill="var(--text-secondary)"
            >
              {point.label}
            </text>
          ))}
          {hover !== null ? (
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={PAD.top}
              y2={H - PAD.bottom}
              stroke="var(--border-strong)"
              strokeWidth={1}
            />
          ) : null}
          {trends.map((trend) => {
            const color = colorOf(models, trend.model)
            const known = trend.points.filter((p) => p.value !== null)
            const path = known.map((p, i) => `${i ? "L" : "M"}${x(p.index)},${y(p.value ?? 0)}`).join(" ")
            return (
              <g key={trend.model}>
                {known.length > 1 ? (
                  <path d={path} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
                ) : null}
                {known.map((p) => (
                  <circle
                    key={p.index}
                    cx={x(p.index)}
                    cy={y(p.value ?? 0)}
                    r={hover === p.index ? 5 : 4}
                    fill={color}
                    stroke="var(--card)"
                    strokeWidth={2}
                  />
                ))}
              </g>
            )
          })}
        </svg>
        {hover !== null ? (
          <div
            className="bg-card ring-border shadow-float pointer-events-none absolute top-2 z-10 min-w-[10rem] rounded-lg p-2.5 text-xs ring-1"
            style={{ left: `${Math.min(70, (x(hover) / W) * 100)}%` }}
          >
            <p className="mb-1 font-semibold">
              {labels[hover]?.label} · {new Date(labels[hover]?.date ?? "").toLocaleDateString()}
            </p>
            {trends.map((trend) => (
              <p key={trend.model} className="flex justify-between gap-3">
                <span className="flex items-center gap-1.5">
                  <span
                    aria-hidden
                    className="size-2 rounded-sm"
                    style={{ background: colorOf(models, trend.model) }}
                  />
                  {trend.model}
                </span>
                <span className="tabular-nums">
                  {trend.points[hover]?.value === null ? "—" : pct(trend.points[hover]?.value ?? 0)}
                </span>
              </p>
            ))}
          </div>
        ) : null}
      </div>
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
                    {point.label} · {new Date(point.date).toLocaleDateString()}
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
