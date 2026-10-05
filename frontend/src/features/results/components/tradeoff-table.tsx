/**
 * The tradeoff table (quality, pass rate, consistency, time, cost per model) with the best
 * value in each column highlighted, and one horizontal bar chart of the pass rate: a single
 * series in one hue (so no legend; the title names it), direct value labels, and a hover
 * tooltip with the counts.
 */
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { ModelMetricsOut } from "@/lib/api/types"
import { formatCost } from "@/lib/format"
import { cn } from "@/lib/utils"

import { RESULTS_COPY } from "../copy"
import { type Column, isBest } from "../insights"
import { comparisonText } from "./comparison-detail"

export const percent = (value: number | null | undefined) =>
  value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`

function Cell({
  models,
  model,
  column,
  children,
}: {
  models: ModelMetricsOut[]
  model: ModelMetricsOut
  column: Column
  children: React.ReactNode
}) {
  const best = isBest(models, model, column)
  return (
    <TableCell className="tabular-nums">
      <span
        className={cn(
          best &&
            "bg-marigold-soft text-marigold-strong ring-marigold/40 rounded-md px-1.5 py-0.5 font-semibold ring-1",
        )}
      >
        {children}
      </span>
    </TableCell>
  )
}

export function TradeoffTable({ models }: { models: ModelMetricsOut[] }) {
  const c = RESULTS_COPY.columns
  const compared = models.some((m) => m.vs_best)
  return (
    <div className="border-border overflow-hidden rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow className="bg-subtle">
            <TableHead>{c.model}</TableHead>
            <TableHead>{c.quality}</TableHead>
            <TableHead>{c.passRate}</TableHead>
            {compared ? <TableHead title={RESULTS_COPY.vsBestHint}>{RESULTS_COPY.vsBest}</TableHead> : null}
            <TableHead title={RESULTS_COPY.consistencyHint}>{c.consistency}</TableHead>
            <TableHead title={RESULTS_COPY.stabilityHint}>{c.stability}</TableHead>
            <TableHead>{c.latency}</TableHead>
            <TableHead>{c.cost}</TableHead>
            <TableHead>{c.perCall}</TableHead>
            <TableHead>{c.failed}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {models.map((m) => (
            <TableRow key={m.model_profile_id}>
              <TableCell className="font-medium">{m.model}</TableCell>
              <Cell models={models} model={m} column="quality">
                {percent(m.quality)}
                {m.unscored_cases > 0 ? (
                  <span className="text-warning-strong block text-xs font-normal">
                    {RESULTS_COPY.judgedCount(m.judged_cases, m.cases)}
                  </span>
                ) : null}
              </Cell>
              <Cell models={models} model={m} column="pass_rate">
                {percent(m.pass_rate)}
              </Cell>
              {compared ? (
                <TableCell className="text-xs">
                  {m.vs_best ? (
                    <span
                      title={comparisonText(m.vs_best)}
                      className={cn(
                        "cursor-help rounded-md px-1.5 py-0.5 ring-1",
                        m.vs_best.label === "clear difference"
                          ? "bg-danger-soft text-danger-strong ring-danger/20 font-semibold"
                          : "bg-subtle text-text-secondary ring-border",
                      )}
                    >
                      {RESULTS_COPY.labels[m.vs_best.label] ?? m.vs_best.label}
                    </span>
                  ) : (
                    <span className="text-text-muted">
                      {isBest(models, m, "quality") ? RESULTS_COPY.bestOnQuality : "—"}
                    </span>
                  )}
                </TableCell>
              ) : null}
              <Cell models={models} model={m} column="consistency">
                {percent(m.consistency)}
              </Cell>
              <TableCell className="tabular-nums">
                {m.stability === null ? (
                  <span className="text-text-muted" title={RESULTS_COPY.stabilityHint}>
                    needs 2+ runs
                  </span>
                ) : (
                  <span title={RESULTS_COPY.stability(m.stable_cases, m.compared_cases)}>
                    {percent(m.stability)}
                    <span className="text-text-muted block text-xs">
                      {RESULTS_COPY.stability(m.stable_cases, m.compared_cases)}
                    </span>
                  </span>
                )}
              </TableCell>
              <Cell models={models} model={m} column="latency_ms">
                {m.latency_ms === null ? "—" : RESULTS_COPY.ms(m.latency_ms)}
              </Cell>
              <TableCell className="tabular-nums">{m.cost === null ? "—" : formatCost(m.cost)}</TableCell>
              <Cell models={models} model={m} column="cost_per_call">
                {m.cost_per_call === null ? "—" : formatCost(m.cost_per_call)}
              </Cell>
              <TableCell
                className={cn(
                  "tabular-nums",
                  m.failed_calls ? "text-danger-strong font-semibold" : undefined,
                )}
              >
                {m.failed_calls}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

export function PassRateChart({ models }: { models: ModelMetricsOut[] }) {
  return (
    <figure className="flex flex-col gap-3" aria-label={RESULTS_COPY.chartTitle}>
      <figcaption className="text-sm font-semibold">{RESULTS_COPY.chartTitle}</figcaption>
      {models.map((m) => {
        const rate = m.pass_rate
        const passed = rate === null ? 0 : Math.round(rate * m.judged_cases)
        return (
          <div
            key={m.model_profile_id}
            className="group relative grid grid-cols-[8rem_1fr_3rem] items-center gap-3 text-sm"
          >
            <span className="text-text-secondary truncate">{m.model}</span>
            <div className="bg-chart-track h-4 rounded-sm">
              <div
                className="bg-chart-1 h-full rounded-r-[4px]"
                style={{ width: `${Math.max(Math.round((rate ?? 0) * 100), 0)}%` }}
              />
            </div>
            <span className="text-right font-medium tabular-nums">{percent(rate)}</span>
            <span
              role="tooltip"
              className="bg-foreground text-background pointer-events-none absolute -top-8 left-32 z-10 hidden rounded-md px-2 py-1 text-xs whitespace-nowrap group-hover:block"
            >
              {rate === null
                ? `${m.model}: nothing could be judged`
                : `${m.model}: ${passed} of ${m.judged_cases} judged passed`}
            </span>
          </div>
        )
      })}
    </figure>
  )
}
