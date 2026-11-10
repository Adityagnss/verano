/** Compare models: quality against cost (with the best value named), speed, and the full tradeoff table. */
"use client"

import { Bar, BarChart, CartesianGrid, LabelList, Scatter, ScatterChart, XAxis, YAxis, ZAxis } from "recharts"

import { Section } from "@/components/common/section"
import { type ChartConfig, ChartContainer, ChartTooltip } from "@/components/ui/chart"
import type { ModelMetricsOut } from "@/lib/api/types"
import { formatCost } from "@/lib/format"

import { RESULTS_COPY, TABS_COPY } from "../copy"
import { bestValue } from "../insights"
import { PassRateChart, percent, TradeoffTable } from "./tradeoff-table"

const config = { value: { label: "Value", color: "var(--color-chart-1)" } } satisfies ChartConfig

function Tip({ active, payload }: { active?: boolean; payload?: { payload: Record<string, unknown> }[] }) {
  const row = active ? payload?.[0]?.payload : undefined
  if (!row) return null
  return (
    <div className="bg-card ring-border rounded-md px-2.5 py-1.5 text-xs shadow-md ring-1">
      <p className="font-medium">{String(row.model)}</p>
      <p>{String(row.text)}</p>
    </div>
  )
}

export function CompareTab({ models, ranked }: { models: ModelMetricsOut[]; ranked: boolean }) {
  const value = bestValue(models)
  const points = models
    .filter((m) => m.quality !== null && m.cost_per_call !== null)
    .map((m) => ({
      model: m.model,
      cost: Number(m.cost_per_call),
      quality: Math.round(Number(m.quality) * 100),
      text: `Quality ${percent(m.quality)}, ${formatCost(m.cost_per_call ?? 0)} per call`,
    }))
  const speed = models
    .filter((m) => m.latency_ms !== null)
    .map((m) => ({
      model: m.model,
      ms: Math.round(Number(m.latency_ms)),
      text: `${RESULTS_COPY.ms(Number(m.latency_ms))} on average`,
    }))
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <Section title={TABS_COPY.qualityCostTitle} description={TABS_COPY.qualityCostHint}>
          {points.length ? (
            <figure aria-label={TABS_COPY.qualityCostTitle} className="flex flex-col gap-2">
              <ChartContainer config={config} className="aspect-auto h-64 w-full">
                <ScatterChart margin={{ top: 16, right: 24, bottom: 8, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    type="number"
                    dataKey="cost"
                    name="Cost per call"
                    tickFormatter={(v: number) => formatCost(v)}
                    tickCount={3}
                  />
                  <YAxis
                    type="number"
                    dataKey="quality"
                    name="Quality"
                    unit="%"
                    domain={[0, 100]}
                    width={40}
                  />
                  <ZAxis range={[90, 90]} />
                  <ChartTooltip content={<Tip />} />
                  <Scatter data={points} fill="var(--color-chart-1)">
                    <LabelList dataKey="model" position="top" className="fill-foreground" fontSize={11} />
                  </Scatter>
                </ScatterChart>
              </ChartContainer>
              {value ? (
                <figcaption className="text-sm font-medium" data-testid="best-value">
                  {TABS_COPY.bestValue(value.model)}
                </figcaption>
              ) : null}
              <p className="text-text-muted text-xs">{TABS_COPY.tableAlt}</p>
            </figure>
          ) : (
            <p className="text-text-muted text-sm">No model has both a quality score and a cost yet.</p>
          )}
        </Section>
        <Section title={TABS_COPY.speedTitle} description={TABS_COPY.tableAlt}>
          {speed.length ? (
            <figure aria-label={TABS_COPY.speedTitle}>
              <ChartContainer
                config={config}
                className="aspect-auto w-full"
                style={{ height: 56 + speed.length * 44 }}
              >
                <BarChart data={speed} layout="vertical" margin={{ left: 0, right: 48 }}>
                  <CartesianGrid horizontal={false} strokeDasharray="3 3" />
                  <XAxis type="number" hide />
                  <YAxis type="category" dataKey="model" width={96} tickLine={false} axisLine={false} />
                  <ChartTooltip cursor={false} content={<Tip />} />
                  <Bar dataKey="ms" fill="var(--color-chart-1)" radius={4}>
                    <LabelList
                      dataKey="ms"
                      position="right"
                      formatter={(v: unknown) => RESULTS_COPY.ms(Number(v))}
                      fontSize={11}
                      className="fill-foreground"
                    />
                  </Bar>
                </BarChart>
              </ChartContainer>
            </figure>
          ) : (
            <p className="text-text-muted text-sm">No timing was recorded.</p>
          )}
        </Section>
      </div>
      <Section title={RESULTS_COPY.tableHeading} description={RESULTS_COPY.tableHint}>
        <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <TradeoffTable models={models} ranked={ranked} />
          <PassRateChart models={models} />
        </div>
      </Section>
    </div>
  )
}
