/** Activity, Explore tab: any measure broken down by any one thing, ranked, with each share of the total. */
"use client"

import { Download } from "lucide-react"

import { Button } from "@/components/ui/button"
import { NativeSelect } from "@/components/ui/select"

import type { Dimension, Metric } from "../domain"
import { DIMENSIONS, METRICS, ranking } from "../domain"
import type { View } from "./activity-page"
import { formatMetric } from "./parts"

const LIMITS = [5, 10, 25, 0]

export interface ExploreState {
  metric: Metric
  dimension: Dimension
  limit: number
}

export function Explore({
  view,
  state,
  onChange,
}: {
  view: View
  state: ExploreState
  onChange: (state: ExploreState) => void
}) {
  const { current, label, colorOf } = view
  const all = ranking(current, state.dimension, state.metric)
  const rows = state.limit ? all.slice(0, state.limit) : all
  const total = all.reduce((a, r) => a + r.value, 0)
  const by = DIMENSIONS.find((d) => d.value === state.dimension)?.label ?? ""
  const measure = METRICS.find((m) => m.value === state.metric)?.label ?? ""

  function download() {
    const lines = [
      [by, measure, "Share of total"],
      ...all.map((r) => [label(state.dimension, r.id).name, String(r.value), r.share.toFixed(4)]),
    ]
    const csv = lines
      .map((line) => line.map((cell) => `"${cell.replaceAll('"', '""')}"`).join(","))
      .join("\n")
    const link = document.createElement("a")
    link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }))
    link.download = `verano-activity-${state.metric}-by-${state.dimension}.csv`
    link.click()
    URL.revokeObjectURL(link.href)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <NativeSelect
          aria-label="Measure"
          value={state.metric}
          onChange={(e) => onChange({ ...state, metric: e.target.value as Metric })}
          className="h-9 w-32"
        >
          {METRICS.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </NativeSelect>
        <span className="text-text-secondary">by</span>
        <NativeSelect
          aria-label="Break down by"
          value={state.dimension}
          onChange={(e) => onChange({ ...state, dimension: e.target.value as Dimension })}
          className="h-9 w-32"
        >
          {DIMENSIONS.map((d) => (
            <option key={d.value} value={d.value}>
              {d.label}
            </option>
          ))}
        </NativeSelect>
        <span className="text-text-secondary ml-2">show</span>
        <NativeSelect
          aria-label="How many"
          value={state.limit}
          onChange={(e) => onChange({ ...state, limit: Number(e.target.value) })}
          className="h-9 w-24"
        >
          {LIMITS.map((n) => (
            <option key={n} value={n}>
              {n ? `Top ${n}` : "All"}
            </option>
          ))}
        </NativeSelect>
        <Button variant="outline" size="sm" className="ml-auto" onClick={download} disabled={!all.length}>
          <Download className="size-4" aria-hidden /> Download CSV
        </Button>
      </div>
      <div className="bg-card border-border overflow-x-auto rounded-xl border">
        <table className="w-full text-sm">
          <caption className="sr-only">
            {measure} by {by.toLowerCase()} in this period
          </caption>
          <thead>
            <tr className="text-text-secondary border-border border-b text-left">
              <th scope="col" className="px-4 py-3 font-medium">
                {by}
              </th>
              <th scope="col" className="px-4 py-3 text-right font-medium">
                {measure}
              </th>
              <th scope="col" className="w-[40%] px-4 py-3 font-medium">
                Share of total
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const name = label(state.dimension, r.id)
              return (
                <tr key={r.id} className="border-border border-b last:border-b-0">
                  <td className="px-4 py-3">
                    <span className="flex items-center gap-2">
                      <span
                        aria-hidden
                        className="size-2.5 shrink-0 rounded-full"
                        style={{ background: colorOf(state.dimension)(r.id) }}
                      />
                      <span className="flex min-w-0 flex-col">
                        <span className="truncate font-medium">{name.name}</span>
                        {name.detail ? (
                          <span className="text-text-muted truncate text-xs">{name.detail}</span>
                        ) : null}
                      </span>
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right font-medium tabular-nums">
                    {formatMetric(state.metric, r.value)}
                  </td>
                  <td className="px-4 py-3">
                    <span className="flex items-center gap-3">
                      <span className="bg-chart-track h-2 flex-1 overflow-hidden rounded-full">
                        <span
                          className="block h-full rounded-full"
                          style={{ width: `${r.share * 100}%`, background: colorOf(state.dimension)(r.id) }}
                        />
                      </span>
                      <span className="text-text-secondary w-14 text-right tabular-nums">
                        {(r.share * 100).toFixed(1)}%
                      </span>
                    </span>
                  </td>
                </tr>
              )
            })}
            {!rows.length ? (
              <tr>
                <td colSpan={3} className="text-text-muted px-4 py-10 text-center">
                  No calls in this period.
                </td>
              </tr>
            ) : null}
          </tbody>
          {rows.length ? (
            <tfoot>
              <tr className="border-border text-text-secondary border-t">
                <td className="px-4 py-3">
                  {state.limit && all.length > state.limit
                    ? `Top ${state.limit} of ${all.length}`
                    : `All ${all.length}`}
                </td>
                <td className="px-4 py-3 text-right font-medium tabular-nums">
                  {formatMetric(state.metric, total)}
                </td>
                <td className="px-4 py-3">Total for the period</td>
              </tr>
            </tfoot>
          ) : null}
        </table>
      </div>
    </div>
  )
}
