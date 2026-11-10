/** Project Home: the pipeline, one "Next step" card, four side cards and the last three runs. */
"use client"

import {
  ArrowRight,
  MessageSquareText,
  Radio,
  ShieldCheck,
  ClipboardCheck,
  type LucideIcon,
} from "lucide-react"
import Link from "next/link"

import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useApps } from "@/features/apps/hooks"
import { useExperiments } from "@/features/run/hooks"
import { useStats } from "@/features/traffic/hooks"
import { useCostSummary, useProject, useStepCompletion } from "@/features/projects/hooks"
import { formatCost } from "@/lib/format"
import { ALL_PROJECT_PAGES } from "@/lib/nav"

import { DONE_STEP, EMPTY_COMPLETION, nextStep, nodeStates, type CardState } from "./home-logic"
import { Pipeline } from "./pipeline"

const STATE_TONE: Record<CardState, "neutral" | "info" | "success"> = {
  "not started": "neutral",
  ready: "info",
  "in progress": "success",
}

function SideCard({
  href,
  icon: Icon,
  title,
  text,
  state,
}: {
  href: string
  icon: LucideIcon
  title: string
  text: string
  state: CardState
}) {
  return (
    <Link
      href={href}
      className="bg-card ring-border hover:ring-lagoon/40 flex min-h-24 flex-col gap-2 rounded-xl p-4 ring-1"
    >
      <span className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 font-medium">
          <Icon className="text-lagoon-strong size-4" aria-hidden />
          {title}
        </span>
        <StatusBadge tone={STATE_TONE[state]}>{state}</StatusBadge>
      </span>
      <span className="text-text-secondary text-sm">{text}</span>
    </Link>
  )
}

function pageLabel(key: string): string {
  return ALL_PROJECT_PAGES.find((p) => p.key === key)?.label ?? key
}

export function ProjectHome({ projectId }: { projectId: string }) {
  const project = useProject(projectId)
  const completion = useStepCompletion(projectId)
  const experiments = useExperiments(projectId)
  const apps = useApps(projectId)
  const stats = useStats(projectId)
  const base = `/projects/${projectId}`
  const done = completion.data ?? EMPTY_COMPLETION
  const states = nodeStates(done)
  const next = nextStep(done) ?? DONE_STEP
  const runs = (experiments.data ?? []).slice(0, 3)
  const appCount = (apps.data ?? []).length
  const traffic = stats.data?.total ?? 0

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">{project.data?.name ?? "Project"}</h1>
        <p className="text-text-secondary text-sm">
          Home: your progress from connecting models to a proven better prompt.
        </p>
      </header>

      <section aria-label="Progress" className="bg-card ring-border rounded-2xl p-5 ring-1 sm:p-6">
        {completion.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <Pipeline base={base} states={states} />
        )}
      </section>

      <section
        aria-labelledby="next-step"
        className="bg-lagoon-soft flex flex-col gap-3 rounded-2xl p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6"
      >
        <div className="min-w-0">
          <p className="text-lagoon-strong text-xs font-semibold tracking-wide uppercase">Next step</p>
          <h2 id="next-step" className="text-xl font-semibold">
            {next.title}
          </h2>
          <p className="text-text-secondary mt-1 max-w-xl text-sm">{next.why}</p>
        </div>
        <Button size="lg" className="min-h-10 shrink-0" render={<Link href={`${base}/${next.segment}`} />}>
          {next.action}
          <ArrowRight className="size-4" aria-hidden />
        </Button>
      </section>

      <section aria-label="More ways to test" className="grid gap-3 sm:grid-cols-2">
        <SideCard
          href={`${base}/apps`}
          icon={MessageSquareText}
          title={pageLabel("apps")}
          text="Test a chatbot, API or RAG app you already run."
          state={appCount > 0 ? "in progress" : "not started"}
        />
        <SideCard
          href={`${base}/traffic`}
          icon={Radio}
          title={pageLabel("traffic")}
          text="Turn real questions from your users into tests."
          state={traffic > 0 ? "in progress" : "not started"}
        />
        <SideCard
          href={`${base}/security`}
          icon={ShieldCheck}
          title={pageLabel("security")}
          text="Try common attacks on your prompt."
          state={done.prompt ? "ready" : "not started"}
        />
        <SideCard
          href={`${base}/review`}
          icon={ClipboardCheck}
          title={pageLabel("review")}
          text="Mark answers good or bad to see if the judge agrees with you."
          state={done.results ? "ready" : "not started"}
        />
      </section>

      <section aria-labelledby="recent-runs" className="flex flex-col gap-2">
        <h2 id="recent-runs" className="text-base font-semibold">
          Latest runs
        </h2>
        {runs.length === 0 ? (
          <p className="text-text-secondary text-sm">No runs yet. Your last three runs will show up here.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {runs.map((run) => (
              <li key={run.id}>
                <Link
                  href={`${base}/results`}
                  className="bg-card ring-border hover:ring-lagoon/40 flex min-h-10 flex-wrap items-center justify-between gap-2 rounded-lg px-4 py-2 ring-1"
                >
                  <span className="min-w-0 truncate font-medium">{run.name}</span>
                  <span className="text-text-secondary flex items-center gap-3 text-xs">
                    <StatusBadge tone={run.status === "completed" ? "success" : "neutral"}>
                      {run.status}
                    </StatusBadge>
                    {new Date(run.created_at).toLocaleDateString()}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
        <CostLine projectId={projectId} />
      </section>
    </div>
  )
}

function CostLine({ projectId }: { projectId: string }) {
  const cost = useCostSummary(projectId)
  if (!cost.data) return null
  return <p className="text-text-muted text-xs">Spent on this project so far: {formatCost(cost.data.cost)}</p>
}
