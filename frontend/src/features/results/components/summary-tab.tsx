/** Summary: the winner in plain words, three headline numbers, and what to do next. */
"use client"

import { Trophy } from "lucide-react"
import Link from "next/link"

import { AnimatedNumber } from "@/components/common/animated-number"
import { buttonVariants } from "@/components/ui/button"
import type { ModelMetricsOut } from "@/lib/api/types"
import { formatCost } from "@/lib/format"

import { RESULTS_COPY, TABS_COPY } from "../copy"
import { bestOn, bestValue, verdict } from "../insights"

function Headline({
  label,
  detail,
  children,
}: {
  label: string
  detail?: string
  children: React.ReactNode
}) {
  return (
    <div className="bg-card border-border flex flex-col gap-1 rounded-xl border p-4">
      <p className="text-text-secondary text-sm">{label}</p>
      <p className="text-3xl font-semibold tabular-nums">{children}</p>
      {detail ? <p className="text-text-muted truncate text-xs">{detail}</p> : null}
    </div>
  )
}

export function SummaryTab({
  projectId,
  experimentId,
  models,
  ranked,
  scored,
}: {
  projectId: string
  experimentId: string
  models: ModelMetricsOut[]
  ranked: boolean
  scored: boolean
}) {
  const v = verdict(models, ranked)
  const value = bestValue(models)
  const cheapest = bestOn(models, "cost_per_call")
  const fastest = bestOn(models, "latency_ms")
  const top = "winner" in v ? v.winner : null
  const base = `/projects/${projectId}`
  const link = buttonVariants({ variant: "outline", size: "lg" })
  return (
    <div className="flex flex-col gap-6">
      <section
        aria-labelledby="winner-title"
        data-testid="winner-card"
        className="bg-card border-border flex flex-col gap-2 rounded-xl border p-5"
      >
        <div className="text-text-secondary flex items-center gap-2 text-sm">
          <Trophy className="text-marigold-strong size-4" aria-hidden />
          <h3 id="winner-title">{TABS_COPY.winnerTitle}</h3>
        </div>
        {top ? <p className="text-2xl font-semibold break-words">{top.model}</p> : null}
        <p className="text-sm">{TABS_COPY.verdict[v.kind]}</p>
        {value && top && value.model_profile_id !== top.model_profile_id ? (
          <p className="text-text-secondary text-sm">{TABS_COPY.bestValue(value.model)}</p>
        ) : null}
      </section>
      <div className="grid gap-3 sm:grid-cols-3">
        <Headline label={TABS_COPY.quality} detail={top?.model}>
          {top && top.quality !== null ? (
            <AnimatedNumber value={Math.round(Number(top.quality) * 100)} suffix="%" />
          ) : (
            "—"
          )}
        </Headline>
        <Headline label={TABS_COPY.cost} detail={cheapest?.model}>
          {cheapest && cheapest.cost_per_call !== null ? (
            <AnimatedNumber value={Number(cheapest.cost_per_call)} format={formatCost} />
          ) : (
            "—"
          )}
        </Headline>
        <Headline label={TABS_COPY.speed} detail={fastest?.model}>
          {fastest && fastest.latency_ms !== null ? (
            <AnimatedNumber value={Number(fastest.latency_ms)} format={RESULTS_COPY.ms} />
          ) : (
            "—"
          )}
        </Headline>
      </div>
      <section aria-labelledby="next-title" className="flex flex-col gap-3">
        <h3 id="next-title" className="text-[1.05rem] font-semibold">
          {TABS_COPY.nextTitle}
        </h3>
        <div className="flex flex-wrap gap-2">
          {scored ? (
            <Link className={link} href={`${base}/improve?experiment=${experimentId}`}>
              {TABS_COPY.nextImprove}
            </Link>
          ) : null}
          <Link className={link} href={`${base}/tests`}>
            {TABS_COPY.nextTests}
          </Link>
          <Link className={link} href={`${base}/review`}>
            {TABS_COPY.nextLabel}
          </Link>
        </div>
      </section>
    </div>
  )
}
