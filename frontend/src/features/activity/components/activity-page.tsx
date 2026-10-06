/**
 * Activity: how the workspace used models, across every project. One request brings the
 * daily rows for the period chosen and the one before it; the tabs only regroup them.
 */
"use client"

import { ArrowLeft } from "lucide-react"
import Link from "next/link"
import { useMemo, useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { Logo } from "@/components/common/logo"
import { NativeSelect } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import type { ActivityRow } from "@/lib/api/types"
import { cn } from "@/lib/utils"
import { AccountMenu } from "@/features/projects/components/account-menu"

import type { Dimension, Metric } from "../domain"
import { daysOf, labeler, palette, split } from "../domain"
import { useActivity } from "../hooks"
import { Explore, type ExploreState } from "./explore"
import { Guardrails } from "./guardrails"
import { Overview } from "./overview"
import { Trends } from "./trends"

const PERIODS = [
  { days: 1, label: "Today", word: "day" },
  { days: 7, label: "Last 7 days", word: "7 days" },
  { days: 30, label: "Last 30 days", word: "30 days" },
  { days: 90, label: "Last 90 days", word: "90 days" },
]
const TABS = ["Overview", "Trends", "Explore", "Guardrails"] as const
type Tab = (typeof TABS)[number]

export interface View {
  current: ActivityRow[]
  prior: ActivityRow[]
  days: string[]
  period: string
  label: ReturnType<typeof labeler>
  colorOf: (dimension: Dimension) => (id: string) => string
}

function browserZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"
  } catch {
    return "UTC"
  }
}

function offsetOf(zone: string): string {
  try {
    const part = new Intl.DateTimeFormat("en-US", { timeZone: zone, timeZoneName: "shortOffset" })
      .formatToParts(new Date())
      .find((p) => p.type === "timeZoneName")
    return part?.value ?? zone
  } catch {
    return zone
  }
}

export function ActivityPage() {
  const local = useMemo(() => browserZone(), [])
  const [days, setDays] = useState(30)
  const [tz, setTz] = useState(local)
  const [projectId, setProjectId] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>("Overview")
  const [explore, setExplore] = useState<ExploreState>({ metric: "spend", dimension: "model", limit: 10 })
  const activity = useActivity(days, tz)
  const data = activity.data

  const view = useMemo<View>(() => {
    const { current, prior } = split(data, projectId)
    const all = [...current, ...prior]
    const colors = new Map<Dimension, (id: string) => string>()
    return {
      current,
      prior,
      days: data ? daysOf(data.start, data.end) : [],
      period: PERIODS.find((p) => p.days === days)?.word ?? `${days} days`,
      label: labeler(data),
      colorOf: (dimension) => {
        if (!colors.has(dimension)) colors.set(dimension, palette(all, dimension))
        return colors.get(dimension)!
      },
    }
  }, [data, projectId, days])

  function openExplore(dimension: Dimension, metric?: Metric) {
    setExplore((state) => ({ ...state, dimension, metric: metric ?? state.metric }))
    setTab("Explore")
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-[96rem] flex-col gap-6 px-4 py-8 sm:px-6 sm:py-10">
      <header className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <Logo size={32} />
          <Link
            href="/projects"
            className="text-text-secondary hover:text-foreground inline-flex items-center gap-1 text-sm"
          >
            <ArrowLeft className="size-4" aria-hidden /> Projects
          </Link>
        </div>
        <AccountMenu />
      </header>

      <div className="border-border flex flex-col gap-5 border-b pb-0">
        <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
          <div className="flex flex-col gap-1.5">
            <h1 className="text-2xl font-semibold tracking-tight sm:text-[1.95rem]">Activity</h1>
            <p className="text-text-secondary max-w-[48rem] text-[0.95rem]">
              Every model call across your projects: what it cost, how much was sent and received, and where
              it went.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <NativeSelect
              aria-label="Project"
              value={projectId ?? ""}
              onChange={(e) => setProjectId(e.target.value || null)}
              className="h-9 w-48"
            >
              <option value="">All projects</option>
              {(data?.projects ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </NativeSelect>
            <NativeSelect
              aria-label="Time zone"
              value={tz}
              onChange={(e) => setTz(e.target.value)}
              className="h-9 w-44"
            >
              <option value={local}>Your time ({offsetOf(local)})</option>
              {local !== "UTC" ? <option value="UTC">UTC</option> : null}
            </NativeSelect>
            <NativeSelect
              aria-label="Period"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="h-9 w-36"
            >
              {PERIODS.map((p) => (
                <option key={p.days} value={p.days}>
                  {p.label}
                </option>
              ))}
            </NativeSelect>
          </div>
        </div>
        <div role="tablist" aria-label="Activity views" className="-mb-px flex gap-1 overflow-x-auto">
          {TABS.map((name) => (
            <button
              key={name}
              type="button"
              role="tab"
              id={`tab-${name}`}
              aria-selected={tab === name}
              aria-controls="activity-panel"
              onClick={() => setTab(name)}
              className={cn(
                "focus-visible:ring-ring/50 border-b-2 px-3 py-2.5 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:outline-none",
                tab === name
                  ? "border-marigold text-foreground"
                  : "text-text-secondary hover:text-foreground border-transparent",
              )}
            >
              {name}
            </button>
          ))}
        </div>
      </div>

      <ErrorMessage error={activity.error} />
      <div id="activity-panel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {activity.isPending ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} className="h-32 rounded-xl" />
            ))}
          </div>
        ) : tab === "Overview" ? (
          <Overview view={view} explore={(dimension) => openExplore(dimension)} />
        ) : tab === "Trends" ? (
          <Trends view={view} explore={openExplore} />
        ) : tab === "Explore" ? (
          <Explore view={view} state={explore} onChange={setExplore} />
        ) : (
          <Guardrails data={data} />
        )}
      </div>
    </main>
  )
}
