/**
 * The tradeoff table (quality, pass rate, consistency, time, cost per model) with the best
 * value in each column highlighted, and one horizontal bar chart of the pass rate: a single
 * series in one hue (so no legend; the title names it), direct value labels, and a hover
 * tooltip with the counts.
 */
import { ResponsiveTable, type ResponsiveColumn } from "@/components/common/responsive-table"
import type { ModelMetricsOut } from "@/lib/api/types"
import { formatCost } from "@/lib/format"
import { cn } from "@/lib/utils"

import { RESULTS_COPY } from "../copy"
import { type Column, isBest } from "../insights"
import { comparisonText } from "./comparison-detail"

export const percent = (value: number | null | undefined) =>
  value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`

function Best({ on, children }: { on: boolean; children: React.ReactNode }) {
  return (
    <span
      className={cn(
        "tabular-nums",
        on &&
          "bg-marigold-soft text-marigold-strong ring-marigold/40 rounded-md px-1.5 py-0.5 font-semibold ring-1",
      )}
    >
      {children}
    </span>
  )
}

/** `ranked` is false when the models were not run alike: no cell is then marked as the best answer quality. */
export function TradeoffTable({ models, ranked = true }: { models: ModelMetricsOut[]; ranked?: boolean }) {
  const c = RESULTS_COPY.columns
  const compared = models.some((m) => m.vs_best)
  const best = (m: ModelMetricsOut, column: Column, needsRank = true) =>
    (!needsRank || ranked) && isBest(models, m, column)
  const columns: ResponsiveColumn<ModelMetricsOut>[] = [
    {
      id: "model",
      header: c.model,
      primary: true,
      cell: (m) => <span className="font-medium">{m.model}</span>,
    },
    {
      id: "quality",
      header: c.quality,
      cell: (m) => (
        <>
          <Best on={best(m, "quality")}>{percent(m.quality)}</Best>
          {m.unscored_cases > 0 ? (
            <span className="text-warning-strong block text-xs font-normal">
              {RESULTS_COPY.judgedCount(m.judged_cases, m.cases)}
            </span>
          ) : null}
        </>
      ),
    },
    {
      id: "pass",
      header: c.passRate,
      cell: (m) => <Best on={best(m, "pass_rate")}>{percent(m.pass_rate)}</Best>,
    },
    ...(compared
      ? [
          {
            id: "vs",
            header: RESULTS_COPY.vsBest,
            cell: (m: ModelMetricsOut) =>
              m.vs_best ? (
                <span
                  title={comparisonText(m.vs_best)}
                  className={cn(
                    "cursor-help rounded-md px-1.5 py-0.5 text-xs ring-1",
                    m.vs_best.label === "clear difference"
                      ? "bg-danger-soft text-danger-strong ring-danger/20 font-semibold"
                      : "bg-subtle text-text-secondary ring-border",
                  )}
                >
                  {RESULTS_COPY.labels[m.vs_best.label] ?? m.vs_best.label}
                </span>
              ) : (
                <span className="text-text-muted text-xs">
                  {ranked && isBest(models, m, "quality") ? RESULTS_COPY.bestOnQuality : "—"}
                </span>
              ),
          },
        ]
      : []),
    {
      id: "consistency",
      header: c.consistency,
      cell: (m) => <Best on={best(m, "consistency")}>{percent(m.consistency)}</Best>,
    },
    {
      id: "stability",
      header: c.stability,
      cell: (m) =>
        m.stability === null ? (
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
        ),
    },
    {
      id: "latency",
      header: c.latency,
      cell: (m) => (
        <Best on={best(m, "latency_ms", false)}>
          {m.latency_ms === null ? "—" : RESULTS_COPY.ms(m.latency_ms)}
        </Best>
      ),
    },
    { id: "cost", header: c.cost, cell: (m) => (m.cost === null ? "—" : formatCost(m.cost)) },
    {
      id: "perCall",
      header: c.perCall,
      cell: (m) => (
        <Best on={best(m, "cost_per_call", false)}>
          {m.cost_per_call === null ? "—" : formatCost(m.cost_per_call)}
        </Best>
      ),
    },
    {
      id: "failed",
      header: c.failed,
      cell: (m) => (
        <span className={cn("tabular-nums", m.failed_calls ? "text-danger-strong font-semibold" : undefined)}>
          {m.failed_calls}
        </span>
      ),
    },
  ]
  return (
    <div className="border-border overflow-x-auto md:rounded-lg md:border">
      <ResponsiveTable
        caption={RESULTS_COPY.tableHeading}
        rows={models}
        rowKey={(m) => m.model_profile_id}
        columns={columns}
      />
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
