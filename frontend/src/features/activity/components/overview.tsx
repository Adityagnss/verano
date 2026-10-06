/** Activity, Overview tab: the headline numbers, where the use came from, and what it was made of. */
"use client"

import { TriangleAlert } from "lucide-react"

import { formatCost, formatTokens } from "@/lib/format"
import type { ActivityRow } from "@/lib/api/types"

import type { Dimension } from "../domain"
import { blendedPerMillion, cacheHitRate, change, daily, parts, ranking, stacked, totals } from "../domain"
import { StackedBars } from "./charts"
import type { View } from "./activity-page"
import { Headline, LinkButton, Panel, RankedList, formatMetric } from "./parts"

const TOKEN_KINDS = [
  { id: "input", color: "var(--series-1)", pick: (r: ActivityRow) => r.input_tokens - r.cached_input_tokens },
  { id: "cached", color: "var(--series-3)", pick: (r: ActivityRow) => r.cached_input_tokens },
  { id: "answer", color: "var(--series-2)", pick: (r: ActivityRow) => r.output_tokens - r.reasoning_tokens },
  { id: "reasoning", color: "var(--series-4)", pick: (r: ActivityRow) => r.reasoning_tokens },
]
const TOKEN_NAMES: Record<string, string> = {
  input: "Prompt (not cached)",
  cached: "Prompt (from cache)",
  answer: "Answer",
  reasoning: "Reasoning",
}
const CACHE_PARTS = [
  {
    id: "uncached",
    color: "var(--series-1)",
    pick: (r: ActivityRow) => r.input_tokens_with_cache_report - r.cached_input_tokens,
  },
  { id: "cached", color: "var(--series-3)", pick: (r: ActivityRow) => r.cached_input_tokens },
]

export function Overview({ view, explore }: { view: View; explore: (dimension: Dimension) => void }) {
  const { current, prior, days, period, label, colorOf } = view
  const now = totals(current)
  const before = totals(prior)
  const hit = cacheHitRate(now)
  const blended = blendedPerMillion(now)
  const keys = ranking(current, "key", "tokens").slice(0, 5)
  const projects = ranking(current, "project", "tokens").slice(0, 5)
  const spendOf = (dimension: Dimension, id: string) =>
    current
      .filter((r) => (dimension === "key" ? (r.key ?? `${r.provider}:no key`) : r.project_id) === id)
      .reduce((a, r) => a + Number(r.cost), 0)
  const name = (dimension: Dimension) => (id: string) =>
    id === "other" ? "Everything else" : label(dimension, id).name

  return (
    <div className="flex flex-col gap-5">
      {now.unknownPrice > 0 ? (
        <p className="border-warning/40 bg-warning-soft text-warning-strong flex items-start gap-2 rounded-lg border px-4 py-3 text-sm">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          {now.unknownPrice.toLocaleString()} calls used a model with no known price, so their cost is not in
          the spend shown.
        </p>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Headline
          label="Spend"
          value={formatCost(now.spend)}
          change={change(now.spend, before.spend)}
          period={period}
          line={daily(current, days, "spend")}
        />
        <Headline
          label="Requests"
          value={now.requests.toLocaleString()}
          detail={now.failed ? `${now.failed.toLocaleString()} failed` : "None failed"}
          change={change(now.requests, before.requests)}
          period={period}
          line={daily(current, days, "requests")}
        />
        <Headline
          label="Tokens"
          value={now.tokens ? formatTokens(now.tokens) : "0"}
          detail={`${formatTokens(now.input)} sent, ${formatTokens(now.output)} received`}
          change={change(now.tokens, before.tokens)}
          period={period}
          line={daily(current, days, "tokens")}
        />
        <Headline
          label="Prompt served from cache"
          value={hit === null ? "Not reported" : `${(hit * 100).toFixed(1)}%`}
          detail={
            hit === null
              ? "These providers don't report caching"
              : `${formatTokens(now.cached)} cached tokens`
          }
          change={change(now.cached, before.cached)}
          period={period}
        />
        <Headline
          label="Cost per million tokens"
          value={blended === null ? "—" : formatCost(blended)}
          detail="Prompt and answer together"
          change={change(blended ?? 0, blendedPerMillion(before) ?? 0)}
          period={period}
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="Top API keys" action={<LinkButton onClick={() => explore("key")}>Explore</LinkButton>}>
          <RankedList
            empty="No calls in this period."
            items={keys.map((k) => ({
              id: k.id,
              ...label("key", k.id),
              color: colorOf("key")(k.id),
              values: [`${formatTokens(k.value) || "0"} tokens`, formatCost(spendOf("key", k.id))],
            }))}
          />
        </Panel>
        <Panel
          title="Top projects"
          action={<LinkButton onClick={() => explore("project")}>Explore</LinkButton>}
        >
          <RankedList
            empty="No calls in this period."
            items={projects.map((p) => ({
              id: p.id,
              ...label("project", p.id),
              color: colorOf("project")(p.id),
              values: [`${formatTokens(p.value) || "0"} tokens`, formatCost(spendOf("project", p.id))],
            }))}
          />
        </Panel>
      </div>

      <Panel
        title="Spend by model"
        action={<LinkButton onClick={() => explore("model")}>Explore</LinkButton>}
      >
        <StackedBars
          label="Spend by model per day"
          data={stacked(current, days, "model", "spend", colorOf("model"))}
          format={(v) => formatMetric("spend", v)}
          name={name("model")}
          empty={now.requests ? "Every call in this period was free." : "No calls in this period."}
        />
      </Panel>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel
          title="Requests by purpose"
          action={<LinkButton onClick={() => explore("purpose")}>Explore</LinkButton>}
        >
          <StackedBars
            label="Requests by purpose per day"
            data={stacked(current, days, "purpose", "requests", colorOf("purpose"))}
            format={(v) => formatMetric("requests", v)}
            name={name("purpose")}
            empty="No calls in this period."
          />
        </Panel>
        <Panel
          title="Requests by model"
          action={<LinkButton onClick={() => explore("model")}>Explore</LinkButton>}
        >
          <StackedBars
            label="Requests by model per day"
            data={stacked(current, days, "model", "requests", colorOf("model"))}
            format={(v) => formatMetric("requests", v)}
            name={name("model")}
            empty="No calls in this period."
          />
        </Panel>
        <Panel title="What the tokens were">
          <StackedBars
            label="Tokens by kind per day"
            data={parts(current, days, TOKEN_KINDS)}
            format={(v) => formatMetric("tokens", v)}
            name={(id) => TOKEN_NAMES[id] ?? id}
            empty="No tokens in this period."
          />
        </Panel>
        <Panel title="Prompt caching">
          <StackedBars
            label="Prompt tokens served from cache per day"
            data={parts(current, days, CACHE_PARTS)}
            format={(v) => formatMetric("tokens", v)}
            name={(id) => (id === "cached" ? "From cache" : "Not cached")}
            empty="None of these providers reported caching."
          />
        </Panel>
      </div>
    </div>
  )
}
