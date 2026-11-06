/** Live scores: the daily pass-rate chart per prompt version, sampling and limit settings, and privacy settings. */
"use client"

import { useState } from "react"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { Section } from "@/components/common/section"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

import { TRAFFIC_COPY as C } from "../copy"
import { linePath, percent, seriesOf } from "../domain"
import { useConfig, useDaily, useRunScoring, useSaveConfig, useStats } from "../hooks"
import type { ConfigOut } from "../types"

const COLORS = [
  "text-brand-strong",
  "text-gold-strong",
  "text-violet-strong",
  "text-info-strong",
  "text-success-strong",
]
const W = 600
const H = 160

function Chart({ projectId }: { projectId: string }) {
  const daily = useDaily(projectId, 30)
  const series = seriesOf(daily.data ?? [], C.scoring.allVersions, C.scoring.unversioned)
  const hasData = series[0]?.points.some((p) => p.rate !== null)
  if (!hasData) return <EmptyState title={C.scoring.chartTitle} description={C.scoring.chartEmpty} />
  const days = series[0].points.map((p) => p.day)
  return (
    <figure className="flex flex-col gap-3">
      <figcaption className="text-sm font-medium">{C.scoring.chartTitle}</figcaption>
      <svg
        viewBox={`-36 -8 ${W + 48} ${H + 36}`}
        role="img"
        aria-label={C.scoring.chartTitle}
        className="w-full"
      >
        {[0, 0.5, 1].map((tick) => (
          <g key={tick} className="text-text-muted">
            <line
              x1={0}
              x2={W}
              y1={(1 - tick) * H}
              y2={(1 - tick) * H}
              stroke="currentColor"
              strokeOpacity={0.2}
            />
            <text x={-6} y={(1 - tick) * H + 4} textAnchor="end" fontSize={10} fill="currentColor">
              {Math.round(tick * 100)}%
            </text>
          </g>
        ))}
        {series.map((s, i) => (
          <path
            key={s.label}
            d={linePath(s.points, W, H)}
            fill="none"
            stroke="currentColor"
            strokeWidth={i === 0 ? 2.5 : 1.5}
            strokeDasharray={i === 0 ? undefined : "4 3"}
            className={COLORS[i % COLORS.length]}
          />
        ))}
        <text x={0} y={H + 16} fontSize={10} fill="currentColor" className="text-text-muted">
          {days[0]}
        </text>
        <text x={W} y={H + 16} fontSize={10} textAnchor="end" fill="currentColor" className="text-text-muted">
          {days[days.length - 1]}
        </text>
      </svg>
      <ul className="flex flex-wrap gap-4 text-xs">
        {series.map((s, i) => (
          <li key={s.label} className={`flex items-center gap-1.5 ${COLORS[i % COLORS.length]}`}>
            <span className="inline-block h-0.5 w-5 bg-current" />
            <span className="text-text-secondary">
              {s.label}: latest {percent([...s.points].reverse().find((p) => p.rate !== null)?.rate)}
            </span>
          </li>
        ))}
      </ul>
    </figure>
  )
}

function Settings({ projectId, config }: { projectId: string; config: ConfigOut }) {
  const save = useSaveConfig(projectId)
  const run = useRunScoring(projectId)
  const stats = useStats(projectId)
  const [draft, setDraft] = useState(config)
  const [patterns, setPatterns] = useState(config.scrub_patterns.join("\n"))
  const set = <K extends keyof ConfigOut>(key: K, value: ConfigOut[K]) =>
    setDraft((d) => ({ ...d, [key]: value }))
  const s = stats.data
  const check = (
    id: string,
    label: string,
    key: "scoring_enabled" | "scrub_pii" | "scrub_emails" | "scrub_phones" | "scrub_cards",
  ) => (
    <label htmlFor={id} className="flex items-center gap-2 text-sm">
      <input id={id} type="checkbox" checked={draft[key]} onChange={(e) => set(key, e.target.checked)} />
      {label}
    </label>
  )
  return (
    <form
      className="flex flex-col gap-6"
      onSubmit={(event) => {
        event.preventDefault()
        save.mutate({
          ...draft,
          scrub_patterns: patterns
            .split("\n")
            .map((p) => p.trim())
            .filter(Boolean),
        })
      }}
    >
      <Section title={C.scoring.title} description={C.scoring.description}>
        {check("scoring-on", C.scoring.switch, "scoring_enabled")}
        {s && !s.has_checks ? <p className="text-warning-strong text-sm">{C.scoring.noChecks}</p> : null}
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rule-rate">{C.scoring.ruleRate} (0 to 1)</Label>
            <Input
              id="rule-rate"
              type="number"
              step="0.05"
              min={0}
              max={1}
              value={draft.rule_sample_rate}
              onChange={(e) => set("rule_sample_rate", Number(e.target.value))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="judge-rate">{C.scoring.judgeRate} (0 to 1)</Label>
            <Input
              id="judge-rate"
              type="number"
              step="0.01"
              min={0}
              max={1}
              value={draft.judge_sample_rate}
              onChange={(e) => set("judge_sample_rate", Number(e.target.value))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="judge-limit">{C.scoring.judgeLimit}</Label>
            <Input
              id="judge-limit"
              type="number"
              min={0}
              value={draft.judge_monthly_limit}
              onChange={(e) => set("judge_monthly_limit", Number(e.target.value))}
            />
          </div>
        </div>
        {s ? (
          <p className="text-text-secondary text-sm">
            {C.scoring.judgeUsed(s.judge_used_this_month, s.judge_monthly_limit)}
            {s.judge_used_this_month >= s.judge_monthly_limit && s.judge_monthly_limit > 0
              ? ` ${C.scoring.limitReached}`
              : ""}
          </p>
        ) : null}
        <div className="flex gap-3">
          <Button type="button" variant="outline" disabled={run.isPending} onClick={() => run.mutate()}>
            {C.scoring.run}
          </Button>
          {run.data ? <p className="self-center text-sm">{run.data.message}</p> : null}
        </div>
      </Section>
      <Section title={C.privacy.title} description={C.privacy.description}>
        {check("scrub-on", C.privacy.scrub, "scrub_pii")}
        <div className="flex flex-wrap gap-4">
          {check("scrub-emails", C.privacy.emails, "scrub_emails")}
          {check("scrub-phones", C.privacy.phones, "scrub_phones")}
          {check("scrub-cards", C.privacy.cards, "scrub_cards")}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="scrub-patterns">{C.privacy.patterns}</Label>
          <textarea
            id="scrub-patterns"
            rows={3}
            className="border-input bg-background rounded-lg border px-3 py-2 font-mono text-xs"
            value={patterns}
            onChange={(e) => setPatterns(e.target.value)}
          />
        </div>
        <div className="flex max-w-xs flex-col gap-1.5">
          <Label htmlFor="retention">{C.privacy.retention}</Label>
          <Input
            id="retention"
            type="number"
            min={1}
            max={365}
            value={draft.retention_days}
            onChange={(e) => set("retention_days", Number(e.target.value))}
          />
        </div>
      </Section>
      <ErrorMessage error={save.error ?? run.error} />
      <div>
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? C.privacy.saving : C.privacy.save}
        </Button>
      </div>
    </form>
  )
}

export function ScoringPanel({ projectId }: { projectId: string }) {
  const config = useConfig(projectId)
  return (
    <div className="flex flex-col gap-6">
      <Section title={C.scoring.chartTitle}>
        <Chart projectId={projectId} />
      </Section>
      {config.data ? (
        <Settings projectId={projectId} config={config.data} key={JSON.stringify(config.data)} />
      ) : (
        <ErrorMessage error={config.error} />
      )}
    </div>
  )
}
