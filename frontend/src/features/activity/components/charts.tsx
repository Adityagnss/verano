/**
 * Activity charts in plain SVG. Daily stacked bars on one axis (never two scales), a legend
 * with every series named (identity is never color alone), a hover read-out per day, and a
 * small sparkline for headline numbers and trend rows. Text stays in ink colors; only marks
 * carry series colors.
 */
"use client"

import { useEffect, useRef, useState } from "react"

import type { Stacked } from "../domain"

const H = 210
const PAD = { left: 64, right: 8, top: 10, bottom: 26 }
const DATE = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" })

export function dayLabel(day: string): string {
  return DATE.format(new Date(`${day}T00:00:00Z`))
}

/** The element's width in pixels, so the chart is drawn at its real size and its text never scales. */
function useWidth(fallback: number) {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(fallback)
  useEffect(() => {
    const element = ref.current
    if (!element) return
    const observer = new ResizeObserver(([entry]) =>
      setWidth(Math.max(240, Math.round(entry.contentRect.width))),
    )
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  return [ref, width] as const
}

function niceMax(max: number): number {
  if (max <= 0) return 1
  const power = 10 ** Math.floor(Math.log10(max))
  const step = [1, 2, 2.5, 5, 10].find((s) => s * power >= max) ?? 10
  return step * power
}

export function StackedBars({
  data,
  label,
  format,
  name,
  empty,
}: {
  data: Stacked
  label: string
  format: (value: number) => string
  name: (id: string) => string
  empty: string
}) {
  const [hover, setHover] = useState<number | null>(null)
  const [box, W] = useWidth(720)
  const totals = data.values.map((day) => Object.values(day).reduce((a, b) => a + b, 0))
  const top = niceMax(Math.max(0, ...totals))
  const count = data.days.length
  const band = (W - PAD.left - PAD.right) / Math.max(count, 1)
  const barWidth = Math.max(2, Math.min(28, band * 0.62))
  const y = (v: number) => PAD.top + (H - PAD.top - PAD.bottom) * (1 - v / top)
  const ticks = [0, top / 2, top]
  const every = Math.max(1, Math.ceil(count / Math.max(2, Math.floor(W / 90))))
  const nothing = totals.every((t) => t === 0)

  return (
    <figure className="flex flex-col gap-3" aria-label={label}>
      <div className="relative" ref={box}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          width={W}
          height={H}
          className="block max-w-full"
          role="img"
          aria-label={label}
        >
          {ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={PAD.left}
                x2={W - PAD.right}
                y1={y(tick)}
                y2={y(tick)}
                stroke="var(--border-color)"
                strokeWidth={1}
                strokeDasharray={tick ? "3 4" : undefined}
              />
              <text x={PAD.left - 8} y={y(tick) + 4} textAnchor="end" fontSize={11} fill="var(--text-muted)">
                {nothing && tick ? "" : format(tick)}
              </text>
            </g>
          ))}
          {data.days.map((day, i) => {
            const x = PAD.left + band * i + (band - barWidth) / 2
            let base = 0
            return (
              <g key={day} opacity={hover === null || hover === i ? 1 : 0.45}>
                {data.series.map((series) => {
                  const v = data.values[i][series.id] ?? 0
                  if (v <= 0) return null
                  const y0 = y(base)
                  base += v
                  const y1 = y(base)
                  return (
                    <rect
                      key={series.id}
                      x={x}
                      y={y1}
                      width={barWidth}
                      height={Math.max(1, y0 - y1)}
                      rx={1.5}
                      fill={series.color}
                      stroke="var(--card)"
                      strokeWidth={1}
                    />
                  )
                })}
                {(count - 1 - i) % every === 0 ? (
                  <text
                    x={i === count - 1 ? x + barWidth : x + barWidth / 2}
                    y={H - 6}
                    textAnchor={i === count - 1 ? "end" : "middle"}
                    fontSize={11}
                    fill="var(--text-secondary)"
                  >
                    {dayLabel(day)}
                  </text>
                ) : null}
                <rect
                  x={PAD.left + band * i}
                  y={PAD.top}
                  width={band}
                  height={H - PAD.top - PAD.bottom}
                  fill="transparent"
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                  onFocus={() => setHover(i)}
                  onBlur={() => setHover(null)}
                  tabIndex={totals[i] > 0 ? 0 : -1}
                  aria-label={`${dayLabel(day)}: ${format(totals[i])}`}
                />
              </g>
            )
          })}
        </svg>
        {nothing ? (
          <p className="text-text-muted pointer-events-none absolute inset-0 flex items-center justify-center text-sm">
            {empty}
          </p>
        ) : null}
        {hover !== null && totals[hover] > 0 ? (
          <div
            className="bg-popover border-border pointer-events-none absolute top-2 z-10 min-w-44 rounded-lg border px-3 py-2 text-xs shadow-md"
            style={
              hover > count / 2
                ? { right: `${((count - hover) / count) * 100}%` }
                : { left: `${((hover + 1) / count) * 100}%` }
            }
          >
            <p className="text-text-secondary mb-1">{dayLabel(data.days[hover])}</p>
            {data.series
              .filter((s) => (data.values[hover][s.id] ?? 0) > 0)
              .map((s) => (
                <p key={s.id} className="flex items-center justify-between gap-4">
                  <span className="flex min-w-0 items-center gap-1.5">
                    <span
                      aria-hidden
                      className="size-2 shrink-0 rounded-sm"
                      style={{ background: s.color }}
                    />
                    <span className="truncate">{name(s.id)}</span>
                  </span>
                  <span className="font-medium tabular-nums">{format(data.values[hover][s.id] ?? 0)}</span>
                </p>
              ))}
          </div>
        ) : null}
      </div>
      {data.series.length ? (
        <figcaption className="border-border flex flex-wrap gap-x-4 gap-y-1.5 border-t pt-3 text-xs">
          {data.series.map((s) => (
            <span key={s.id} className="flex items-center gap-1.5">
              <span aria-hidden className="size-2.5 rounded-sm" style={{ background: s.color }} />
              <span>{name(s.id)}</span>
              <span className="text-text-muted tabular-nums">{format(s.total)}</span>
            </span>
          ))}
        </figcaption>
      ) : null}
    </figure>
  )
}

export function Sparkline({ values, label }: { values: number[]; label: string }) {
  const w = 96
  const h = 28
  const max = Math.max(0, ...values)
  if (values.length < 2) return null
  const points = values
    .map(
      (v, i) =>
        `${((i / (values.length - 1)) * (w - 2) + 1).toFixed(1)},${(h - 2 - (max ? (v / max) * (h - 4) : 0)).toFixed(1)}`,
    )
    .join(" ")
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-7 w-24 shrink-0" role="img" aria-label={label}>
      <polyline
        points={points}
        fill="none"
        stroke="var(--series-1)"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  )
}
