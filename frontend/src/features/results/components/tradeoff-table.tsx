/**
 * The tradeoff table (quality, pass rate, consistency, time, cost per model) and one bar
 * chart of the pass rate, in blue shades only (DEVELOPMENT.md C2).
 */
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { ModelMetricsOut } from "@/lib/api/types"
import { formatCost } from "@/lib/format"

import { RESULTS_COPY } from "../copy"

const percent = (value: number | null | undefined) =>
  value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`

export function TradeoffTable({ models }: { models: ModelMetricsOut[] }) {
  const c = RESULTS_COPY.columns
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{c.model}</TableHead>
          <TableHead>{c.quality}</TableHead>
          <TableHead>{c.passRate}</TableHead>
          <TableHead title={RESULTS_COPY.consistencyHint}>{c.consistency}</TableHead>
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
            <TableCell>{percent(m.quality)}</TableCell>
            <TableCell>{percent(m.pass_rate)}</TableCell>
            <TableCell>{percent(m.consistency)}</TableCell>
            <TableCell>{m.latency_ms === null ? "—" : RESULTS_COPY.ms(m.latency_ms)}</TableCell>
            <TableCell>{m.cost === null ? "—" : formatCost(m.cost)}</TableCell>
            <TableCell>{m.cost_per_call === null ? "—" : formatCost(m.cost_per_call)}</TableCell>
            <TableCell className={m.failed_calls ? "text-destructive" : undefined}>
              {m.failed_calls}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export function PassRateChart({ models }: { models: ModelMetricsOut[] }) {
  return (
    <figure className="flex flex-col gap-2" aria-label={RESULTS_COPY.chartTitle}>
      <figcaption className="text-sm font-medium">{RESULTS_COPY.chartTitle}</figcaption>
      {models.map((m) => (
        <div key={m.model_profile_id} className="grid grid-cols-[10rem_1fr_3rem] items-center gap-3 text-sm">
          <span className="truncate">{m.model}</span>
          <div className="bg-secondary h-3 overflow-hidden rounded-full">
            <div
              className="h-full bg-[var(--brand-accent)]"
              style={{ width: `${Math.round(m.pass_rate * 100)}%` }}
            />
          </div>
          <span className="text-right">{percent(m.pass_rate)}</span>
        </div>
      ))}
    </figure>
  )
}
