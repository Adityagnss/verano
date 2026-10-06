/** Activity, Trends tab: use over time by model, key and project, and what moved against the period before. */
"use client"

import { useState } from "react"

import { NativeSelect } from "@/components/ui/select"

import type { Dimension, Metric } from "../domain"
import { METRICS, stacked, trending } from "../domain"
import { StackedBars } from "./charts"
import type { View } from "./activity-page"
import { ChangeLine, LinkButton, Panel, formatMetric } from "./parts"
import { Sparkline } from "./charts"

const SECTIONS: { dimension: Dimension; title: string }[] = [
  { dimension: "model", title: "Models" },
  { dimension: "key", title: "API keys" },
  { dimension: "project", title: "Projects" },
]

export function Trends({
  view,
  explore,
}: {
  view: View
  explore: (dimension: Dimension, metric: Metric) => void
}) {
  return (
    <div className="flex flex-col gap-8">
      {SECTIONS.map((section) => (
        <TrendSection key={section.dimension} view={view} explore={explore} {...section} />
      ))}
    </div>
  )
}

function TrendSection({
  view,
  dimension,
  title,
  explore,
}: {
  view: View
  dimension: Dimension
  title: string
  explore: (dimension: Dimension, metric: Metric) => void
}) {
  const [metric, setMetric] = useState<Metric>(dimension === "model" ? "requests" : "spend")
  const { current, prior, days, period, label, colorOf } = view
  const movers = trending(current, prior, days, dimension, metric).slice(0, 6)
  const metricName = METRICS.find((m) => m.value === metric)?.label ?? metric
  const name = (id: string) => (id === "other" ? "Everything else" : label(dimension, id).name)
  return (
    <section className="flex flex-col gap-3" aria-label={title}>
      <header className="flex items-center justify-between gap-3">
        <h3 className="text-lg font-semibold">{title}</h3>
        <label className="flex items-center gap-2 text-sm">
          <span className="text-text-secondary">Show</span>
          <NativeSelect
            value={metric}
            onChange={(e) => setMetric(e.target.value as Metric)}
            className="h-9 w-32"
          >
            {METRICS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </NativeSelect>
        </label>
      </header>
      <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Panel
          title={`${metricName} over time`}
          action={<LinkButton onClick={() => explore(dimension, metric)}>Explore</LinkButton>}
        >
          <StackedBars
            label={`${metricName} by ${title.toLowerCase()} per day`}
            data={stacked(current, days, dimension, metric, colorOf(dimension))}
            format={(v) => formatMetric(metric, v)}
            name={name}
            empty={
              metric === "spend" && current.length
                ? "Every call in this period was free."
                : "No calls in this period."
            }
          />
        </Panel>
        <Panel title="Biggest changes">
          {movers.length ? (
            <ul className="flex flex-col">
              {movers.map((t) => (
                <li
                  key={t.id}
                  className="border-border flex items-center gap-3 border-t py-2.5 first:border-t-0"
                >
                  <span
                    aria-hidden
                    className="size-2.5 shrink-0 rounded-full"
                    style={{ background: colorOf(dimension)(t.id) }}
                  />
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate text-sm font-medium">{name(t.id)}</span>
                    <span className="text-xs">
                      <ChangeLine change={t.change} period={period} />
                    </span>
                  </span>
                  <Sparkline values={t.line} label={`${name(t.id)}, ${metricName.toLowerCase()} per day`} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-text-muted py-8 text-center text-sm">
              Nothing changed by a tenth or more against the {period} before.
            </p>
          )}
        </Panel>
      </div>
    </section>
  )
}
