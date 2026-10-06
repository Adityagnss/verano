/**
 * Charts and findings for whatever the filters select. Every measure has its own small chart
 * (never two scales on one axis), every chart is labelled in plain words, and the full numbers
 * are one click away in a table. Numbers come from the same records as the Answers table.
 */
"use client"

import { Lightbulb } from "lucide-react"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { Section } from "@/components/common/section"
import { StatTile } from "@/components/common/stat-tile"
import { Skeleton } from "@/components/ui/skeleton"
import { ModelBars, TrendChart, colorOf } from "@/features/dashboard/components/charts"
import { usd } from "@/features/dashboard/domain"
import type { AnalysisOut, GroupStats, LogOptions } from "@/lib/api/types"
import { formatMs, versionName } from "@/lib/format"

import { type AnswerFilters, findings, grid } from "../domain"
import { useAnalysis } from "../hooks"
import { FilterBar } from "./filter-bar"

const pct = (v: number) => `${Math.round(v * 100)}%`

type PerModel = {
  model: string
  answers: number
  passed: number
  judged: number
  quality: number | null
  golden: number | null
  cost: number | null
  latency: number | null
  p50: number | null
  p90: number | null
}

function perModel(groups: GroupStats[]): PerModel[] {
  const names = [...new Set(groups.map((g) => g.model))].sort()
  return names.map((model) => {
    const rows = groups.filter((g) => g.model === model)
    const answers = rows.reduce((s, g) => s + g.answers, 0)
    const weighted = (pick: (g: GroupStats) => number | null) => {
      const usable = rows.filter((g) => pick(g) !== null)
      const weight = usable.reduce((s, g) => s + g.answers, 0)
      return weight ? usable.reduce((s, g) => s + (pick(g) ?? 0) * g.answers, 0) / weight : null
    }
    const priced = rows.every((g) => g.cost !== null)
    return {
      model,
      answers,
      passed: rows.reduce((s, g) => s + g.passed, 0),
      judged: rows.reduce((s, g) => s + g.judged, 0),
      quality: weighted((g) => g.quality),
      golden: weighted((g) => g.golden_match),
      cost: priced && answers ? rows.reduce((s, g) => s + Number(g.cost), 0) / answers : null,
      latency: weighted((g) => g.avg_latency_ms),
      p50: weighted((g) => g.p50_latency_ms),
      p90: weighted((g) => g.p90_latency_ms),
    }
  })
}

function Heat({ analysis }: { analysis: AnalysisOut }) {
  const { versions, models, cells } = grid(analysis.groups)
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[24rem] border-separate border-spacing-1 text-sm">
        <thead>
          <tr className="text-text-secondary text-xs">
            <th className="px-2 py-1 text-left font-medium">Model</th>
            {versions.map((v) => (
              <th key={v} className="px-2 py-1 text-center font-medium">
                Prompt v{v}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {models.map((model) => (
            <tr key={model}>
              <th className="flex items-center gap-2 px-2 py-2 text-left font-medium">
                <span
                  aria-hidden
                  className="size-2.5 rounded-sm"
                  style={{ background: colorOf(models, model) }}
                />
                {model}
              </th>
              {versions.map((v) => {
                const cell = cells.get(`${model}|${v}`)
                const rate = cell?.rate ?? null
                return (
                  <td
                    key={v}
                    title={cell ? `${cell.answers} answers` : "not tested"}
                    className="rounded-lg px-2 py-2 text-center tabular-nums"
                    style={{
                      background:
                        rate === null ? "var(--bg-subtle)" : `rgb(37 99 235 / ${0.08 + rate * 0.62})`,
                      color: rate !== null && rate > 0.6 ? "#fff" : "var(--text-primary)",
                    }}
                  >
                    {rate === null ? "—" : pct(rate)}
                    {cell ? (
                      <span className="block text-[10px] opacity-75">{cell.answers} answers</span>
                    ) : null}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function AnalysisTab({
  projectId,
  options,
  filters,
  onFilters,
}: {
  projectId: string
  options: LogOptions | undefined
  filters: AnswerFilters
  onFilters: (filters: AnswerFilters) => void
}) {
  const query = useAnalysis(projectId, filters, true)
  const analysis = query.data
  const models = analysis ? [...new Set(analysis.groups.map((g) => g.model))] : []
  const per = analysis ? perModel(analysis.groups) : []
  const versions = analysis
    ? [...new Set(analysis.groups.map((g) => g.prompt_version))].sort((a, b) => a - b)
    : []
  const rows = (pick: (m: PerModel) => number | null) =>
    per.map((m) => ({ model: m.model, color: colorOf(models, m.model), value: pick(m) }))
  const trend = models.map((model) => ({
    model,
    points: versions.map((v, index) => ({
      index,
      label: versionName(v),
      date: "",
      value: analysis?.groups.find((g) => g.model === model && g.prompt_version === v)?.pass_rate ?? null,
    })),
  }))
  const totals = analysis?.totals
  return (
    <div className="flex flex-col gap-4">
      <FilterBar options={options} filters={filters} onChange={onFilters} total={totals?.answers} />
      <ErrorMessage error={query.error} />
      {query.isPending ? <Skeleton className="h-72 w-full" /> : null}
      {analysis && totals && totals.answers === 0 ? (
        <EmptyState
          title="Nothing to analyse"
          description="No answers match these filters. Loosen a filter, or run an experiment first."
        />
      ) : null}
      {analysis && totals && totals.answers > 0 ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <StatTile
              label="Answers"
              value={totals.answers.toLocaleString()}
              detail={`${totals.experiments} runs · ${totals.models} models`}
            />
            <StatTile
              label="Passed"
              value={pct(totals.passed / totals.answers)}
              detail={`${totals.passed.toLocaleString()} of ${totals.answers.toLocaleString()}`}
              winner
            />
            <StatTile
              label="Failed calls"
              value={totals.failed_calls.toLocaleString()}
              detail="calls that errored"
            />
            <StatTile
              label="Spent"
              value={totals.cost === null ? "unknown" : usd(Number(totals.cost))}
              detail={
                totals.unknown_price_answers
                  ? `${totals.unknown_price_answers} answers unpriced`
                  : "these answers only"
              }
            />
            <StatTile
              label="Tokens"
              value={(totals.input_tokens + totals.output_tokens).toLocaleString()}
              detail={`${totals.input_tokens.toLocaleString()} in · ${totals.output_tokens.toLocaleString()} out`}
            />
          </div>
          <div className="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <Section
              title="Pass rate by model and prompt version"
              description="Darker blue means a higher share of answers passed. Empty cells were not tested."
            >
              <Heat analysis={analysis} />
            </Section>
            <Section title="What this tells you">
              <ul className="flex flex-col gap-3">
                {findings(analysis).map((note) => (
                  <li key={note} className="flex gap-2.5 text-sm leading-snug">
                    <Lightbulb className="text-lagoon-strong mt-0.5 size-4 shrink-0" />
                    {note}
                  </li>
                ))}
              </ul>
            </Section>
          </div>
          {versions.length >= 2 ? (
            <Section
              title="Is the prompt getting better?"
              description="Pass rate of each model on each prompt version, oldest to newest."
            >
              <TrendChart trends={trend} models={models} />
            </Section>
          ) : null}
          <Section
            title="Models compared"
            description="One small chart per measure, each on its own scale. Averages over the selected answers."
          >
            <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
              <ModelBars
                title="Passed"
                hint="Share of answers where every check passed. Higher is better."
                rows={rows((m) => (m.judged ? m.passed / m.judged : null))}
                format={pct}
              />
              <ModelBars
                title="Golden match"
                hint="Share of the golden JSON's fields matched exactly. Higher is better."
                rows={rows((m) => m.golden)}
                format={pct}
              />
              <ModelBars
                title="Quality"
                hint="Average score of the checks. Higher is better."
                rows={rows((m) => m.quality)}
                format={pct}
              />
              <ModelBars
                title="Cost per answer"
                hint="Lower is better. Unknown when a price is missing."
                rows={rows((m) => m.cost)}
                format={usd}
              />
              <ModelBars
                title="Typical time (median)"
                hint="Half of the answers were faster than this."
                rows={rows((m) => m.p50)}
                format={formatMs}
              />
              <ModelBars
                title="Slowest 10% (90th percentile)"
                hint="Nine in ten answers were faster than this."
                rows={rows((m) => m.p90)}
                format={formatMs}
              />
            </div>
          </Section>
          {analysis.failed_checks.length > 0 ? (
            <Section title="Which checks fail most" description="How many answers failed each scoring check.">
              <ModelBars
                title="Failures by check"
                hint="Higher means that check catches more answers."
                rows={analysis.failed_checks.map((c) => ({
                  model: c.check.replaceAll("_", " "),
                  color: "var(--series-1)",
                  value: c.failures,
                }))}
                format={(v) => `${v.toLocaleString()} answers`}
              />
            </Section>
          ) : null}
          <Section
            title="All the numbers"
            description="Everything above as a table, one row per prompt version and model."
          >
            <div className="overflow-x-auto">
              <table className="w-full min-w-[60rem] text-left text-sm">
                <thead className="text-text-secondary text-xs">
                  <tr>
                    {[
                      "Prompt",
                      "Model",
                      "Answers",
                      "Passed",
                      "Pass rate",
                      "Quality",
                      "Golden match",
                      "Failed calls",
                      "Cost",
                      "Avg time",
                      "Median",
                      "Slowest 10%",
                      "Tokens in / out",
                    ].map((h) => (
                      <th key={h} className="py-2 pr-4 font-medium whitespace-nowrap">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {analysis.groups.map((g) => (
                    <tr
                      key={`${g.prompt_version}-${g.model}`}
                      className="border-border border-t tabular-nums"
                    >
                      <td className="py-2 pr-4">{versionName(g.prompt_version)}</td>
                      <td className="py-2 pr-4 font-medium">{g.model}</td>
                      <td className="py-2 pr-4">{g.answers}</td>
                      <td className="py-2 pr-4">{g.passed}</td>
                      <td className="py-2 pr-4">{g.pass_rate === null ? "—" : pct(g.pass_rate)}</td>
                      <td className="py-2 pr-4">{g.quality === null ? "—" : pct(g.quality)}</td>
                      <td className="py-2 pr-4">{g.golden_match === null ? "—" : pct(g.golden_match)}</td>
                      <td className="py-2 pr-4">{g.failed_calls}</td>
                      <td className="py-2 pr-4">{g.cost === null ? "unknown" : usd(Number(g.cost))}</td>
                      <td className="py-2 pr-4">
                        {g.avg_latency_ms === null ? "—" : formatMs(g.avg_latency_ms)}
                      </td>
                      <td className="py-2 pr-4">
                        {g.p50_latency_ms === null ? "—" : formatMs(g.p50_latency_ms)}
                      </td>
                      <td className="py-2 pr-4">
                        {g.p90_latency_ms === null ? "—" : formatMs(g.p90_latency_ms)}
                      </td>
                      <td className="py-2 pr-4">
                        {g.input_tokens.toLocaleString()} / {g.output_tokens.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        </>
      ) : null}
    </div>
  )
}
