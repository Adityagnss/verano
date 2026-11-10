/**
 * The project dashboard: how prompts and models are doing, in one place. Headline numbers,
 * the latest experiment side by side (pass rate, cost per call, time per call), pass rate
 * across prompt versions, where the money went, and plain-language findings.
 */
"use client"

import { Lightbulb } from "lucide-react"
import Link from "next/link"
import { useState } from "react"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { Section } from "@/components/common/section"
import { StatTile } from "@/components/common/stat-tile"
import { StatusBadge } from "@/components/common/status-badge"
import { PageIntro } from "@/components/common/page-intro"
import { buttonVariants } from "@/components/ui/button"
import { ALL_PROJECT_PAGES } from "@/lib/nav"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { defaultPrompt, forPrompt, promptsOf } from "@/features/prompts-choice/domain"
import { unfairReasons } from "@/lib/fairness"
import { formatMs } from "@/lib/format"

import { useDashboardData } from "../hooks"
import {
  finishedExperiments,
  insights,
  latestPerVersion,
  pct,
  spend,
  trends,
  usd,
  versionLabels,
  yourRuns,
} from "../domain"
import { ModelBars, SpendBar, TrendChart, colorOf } from "./charts"
import { VersionsPanel, useComparison } from "./versions-panel"

const PAGE = ALL_PROJECT_PAGES.find((p) => p.key === "dashboard")!

export function DashboardPage({ projectId }: { projectId: string }) {
  const data = useDashboardData(projectId)
  // Versions are compared within one prompt: with several prompts, one is chosen (the newest run's by default).
  const [pickedPrompt, setPickedPrompt] = useState("")
  const prompts = promptsOf(data.experiments)
  const promptId = prompts.length < 2 ? null : pickedPrompt || defaultPrompt(data.experiments)
  const finished = yourRuns(
    finishedExperiments(forPrompt(data.experiments, promptId), data.results, versionLabels(data.versions)),
  )
  const compared = latestPerVersion(finished).slice(-2)
  const proof = useComparison(
    projectId,
    compared[1]?.experiment.id ?? null,
    compared[0]?.experiment.id ?? null,
  )
  const latest = finished.at(-1)
  const models = [...new Set(finished.flatMap((f) => f.results.models.map((m) => m.model)))]
  const parts = spend(data.cost)
  const notes = insights(finished, data.cost, proof.data ?? null)
  const rates = (latest?.results.models ?? []).map((m) => m.pass_rate).filter((r): r is number => r !== null)
  const best = rates.length ? Math.max(...rates) : null
  const rows = (pick: (m: NonNullable<typeof latest>["results"]["models"][number]) => number | null) =>
    (latest?.results.models ?? []).map((m) => ({
      model: m.model,
      color: colorOf(models, m.model),
      value: pick(m),
    }))

  return (
    <div className="mx-auto flex w-full max-w-[96rem] min-w-0 flex-col gap-6">
      <PageIntro
        storageKey="dashboard"
        title={PAGE.label}
        what="How your prompts and models change over time: pass rate, cost, speed and prompt versions."
        whenToUse="you have run the test more than once and want to know if things are getting better"
        youGet="a chart of pass rate across runs, a side-by-side of your latest run, and plain-language findings"
        primaryAction={
          latest ? undefined : (
            <Link href={`/projects/${projectId}/run`} className={buttonVariants({ size: "lg" })}>
              Run the test
            </Link>
          )
        }
        learnMore="dashboard"
        hasContent={finished.length > 0}
      />
      <ErrorMessage error={data.error} />
      {prompts.length > 1 ? (
        <div className="flex max-w-md flex-col gap-1.5">
          <Label htmlFor="dashboard-prompt">Prompt</Label>
          <NativeSelect
            id="dashboard-prompt"
            value={promptId ?? ""}
            onChange={(e) => setPickedPrompt(e.target.value)}
          >
            {prompts.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </NativeSelect>
          <p className="text-text-muted text-xs">
            Versions and trends are only compared within one prompt. Pick another to see its own.
          </p>
        </div>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Spent on models"
          value={usd(Number(data.cost?.cost ?? 0))}
          detail={`${(data.cost?.calls ?? 0).toLocaleString()} model calls`}
        />
        <StatTile
          label="Your experiments finished"
          value={finished.length}
          detail={latest ? `latest: ${latest.label}` : "none yet"}
        />
        <StatTile
          label="Best pass rate (your latest run)"
          value={best === null ? "—" : pct(best)}
          detail={latest ? `${latest.results.models.length} models compared` : "run an experiment first"}
          winner={best !== null && !(latest && unfairReasons(latest.experiment).length)}
        />
        <StatTile label="Prompt versions" value={data.versions.length} detail="saved so far" />
      </div>

      {data.loading && finished.length === 0 ? <Skeleton className="h-56 w-full" /> : null}
      {!data.loading && !latest ? (
        <EmptyState
          title="Nothing to show yet"
          description="Run the test on your models. This page fills in as soon as one run finishes."
          action={
            <Link href={`/projects/${projectId}/run`} className={buttonVariants({ size: "lg" })}>
              Run the test
            </Link>
          }
        />
      ) : null}

      {latest ? (
        <>
          <Section
            title="Latest experiment: models side by side"
            description={`${latest.label} · ${new Date(latest.experiment.created_at).toLocaleString()} · each measure has its own scale`}
            action={
              <Link
                href={`/projects/${projectId}/results`}
                className="text-lagoon-strong text-sm font-medium"
              >
                Compare results →
              </Link>
            }
          >
            <div className="grid gap-6 md:grid-cols-3">
              <ModelBars
                title="Passed"
                hint="Share of test cases where every required check passed. Higher is better."
                rows={rows((m) => m.pass_rate)}
                format={pct}
              />
              <ModelBars
                title="Cost per call"
                hint="What one answer costs. Lower is better."
                rows={rows((m) => (m.cost_per_call === null ? null : Number(m.cost_per_call)))}
                format={usd}
              />
              <ModelBars
                title="Time per call"
                hint="Average time to answer. Lower is better."
                rows={rows((m) => m.latency_ms)}
                format={formatMs}
              />
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[32rem] text-left text-sm">
                <thead>
                  <tr className="text-text-secondary text-xs">
                    <th className="py-2 pr-4 font-medium">Model</th>
                    <th className="py-2 pr-4 font-medium">Quality</th>
                    <th className="py-2 pr-4 font-medium">How consistent</th>
                    <th className="py-2 pr-4 font-medium">Failed calls</th>
                    <th className="py-2 pr-4 font-medium">Total cost</th>
                  </tr>
                </thead>
                <tbody>
                  {latest.results.models.map((m) => (
                    <tr key={m.model_profile_id} className="border-border border-t">
                      <td className="py-2 pr-4 font-medium">{m.model}</td>
                      <td className="py-2 pr-4 tabular-nums">{pct(m.quality)}</td>
                      <td className="py-2 pr-4 tabular-nums">
                        {m.consistency === null ? "needs 2+ runs" : pct(m.consistency)}
                      </td>
                      <td className="py-2 pr-4">
                        {m.failed_calls > 0 ? (
                          <StatusBadge tone="danger">{m.failed_calls} failed</StatusBadge>
                        ) : (
                          <span className="text-text-secondary">none</span>
                        )}
                      </td>
                      <td className="py-2 pr-4 tabular-nums">
                        {m.cost === null ? "unknown" : usd(Number(m.cost))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          <Section
            title="Prompt versions"
            description="How each prompt version did, and any two runs compared case by case."
          >
            <VersionsPanel projectId={projectId} finished={finished} />
          </Section>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <Section
              title="Is the prompt getting better?"
              description="Pass rate of each model in every finished experiment, oldest to newest. The label is the prompt version tested."
            >
              <TrendChart trends={trends(finished)} models={models} />
            </Section>
            <div className="flex flex-col gap-6">
              <Section title="What this tells you">
                <ul className="flex flex-col gap-3">
                  {notes.map((note) => (
                    <li key={note} className="flex gap-2.5 text-sm leading-snug">
                      <Lightbulb className="text-lagoon-strong mt-0.5 size-4 shrink-0" />
                      {note}
                    </li>
                  ))}
                </ul>
              </Section>
              <Section title="Where the money went" description="All model calls in this project.">
                {parts.length ? (
                  <SpendBar parts={parts} format={usd} />
                ) : (
                  <p className="text-text-secondary text-sm">Nothing spent yet.</p>
                )}
              </Section>
            </div>
          </div>
        </>
      ) : null}
    </div>
  )
}
