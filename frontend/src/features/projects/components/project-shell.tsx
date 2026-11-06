/**
 * The frame around every project step (DEVELOPMENT.md C3): logo and stepper on the left
 * (a slide-over menu below the lg breakpoint), a breadcrumb with the project name and the project's running LLM cost at the top, the
 * step's content below.
 * When some calls used models with an unknown price, the cost says so instead of looking
 * complete.
 */
"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Activity, BookOpen, LayoutDashboard, Menu, Plug, Table2, X } from "lucide-react"
import { type ReactNode, useState } from "react"

import { COMMON_COPY } from "@/components/common/copy"
import { Button } from "@/components/ui/button"
import { Logo } from "@/components/common/logo"
import { type StepItem, type StepState, Stepper } from "@/components/common/stepper"
import { formatCost } from "@/lib/format"
import { type StepKey, STEPS } from "@/lib/steps"

import { useCostSummary, useProject, useStepCompletion } from "../hooks"
import { AccountMenu } from "./account-menu"

function stepItems(projectId: string, pathname: string, done: Partial<Record<StepKey, boolean>>): StepItem[] {
  const firstOpen = STEPS.find((step) => step.available && !done[step.key])?.key
  return STEPS.map((step, index) => {
    const href = `/projects/${projectId}/${step.segment}`
    const current = pathname.startsWith(href)
    const state: StepState = !step.available
      ? "unavailable"
      : current
        ? "current"
        : done[step.key]
          ? "done"
          : step.key === firstOpen
            ? "next"
            : "upcoming"
    return { key: step.key, number: index + 1, label: step.label, hint: step.hint, href, state }
  })
}

function ToolLinks({ projectId, pathname }: { projectId: string; pathname: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <p className="text-text-muted px-3 pb-1 text-[11px] font-semibold tracking-wider uppercase">Tools</p>
      <DashboardLink projectId={projectId} active={pathname.endsWith("/dashboard")} />
      <AppsLink projectId={projectId} active={pathname.endsWith("/apps")} />
      <LogbookLink projectId={projectId} active={pathname.endsWith("/logbook")} />
      <GuideLink projectId={projectId} active={pathname.endsWith("/guide")} />
      <Link
        href="/activity"
        className="hover:bg-subtle flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors"
      >
        <Activity className="text-lagoon-strong size-4" />
        <span className="flex flex-col leading-tight">
          Activity
          <span className="text-text-muted text-xs font-normal">Usage across all projects</span>
        </span>
      </Link>
    </div>
  )
}

function DashboardLink({ projectId, active }: { projectId: string; active: boolean }) {
  return (
    <Link
      href={`/projects/${projectId}/dashboard`}
      aria-current={active ? "page" : undefined}
      className={`hover:bg-subtle flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${active ? "bg-lagoon-soft font-semibold" : "font-medium"}`}
    >
      <LayoutDashboard className="text-lagoon-strong size-4" />
      <span className="flex flex-col leading-tight">
        Dashboard
        <span className="text-text-muted text-xs font-normal">Models, cost, trends</span>
      </span>
    </Link>
  )
}

function AppsLink({ projectId, active }: { projectId: string; active: boolean }) {
  return (
    <Link
      href={`/projects/${projectId}/apps`}
      aria-current={active ? "page" : undefined}
      className={`hover:bg-subtle flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${active ? "bg-lagoon-soft font-semibold" : "font-medium"}`}
    >
      <Plug className="text-lagoon-strong size-4" />
      <span className="flex flex-col leading-tight">
        Your apps
        <span className="text-text-muted text-xs font-normal">Test your own app over HTTP</span>
      </span>
    </Link>
  )
}

function LogbookLink({ projectId, active }: { projectId: string; active: boolean }) {
  return (
    <Link
      href={`/projects/${projectId}/logbook`}
      aria-current={active ? "page" : undefined}
      className={`hover:bg-subtle flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${active ? "bg-lagoon-soft font-semibold" : "font-medium"}`}
    >
      <Table2 className="text-lagoon-strong size-4" />
      <span className="flex flex-col leading-tight">
        Logbook
        <span className="text-text-muted text-xs font-normal">Every answer and call</span>
      </span>
    </Link>
  )
}

function GuideLink({ projectId, active }: { projectId: string; active: boolean }) {
  return (
    <Link
      href={`/projects/${projectId}/guide`}
      aria-current={active ? "page" : undefined}
      className={`hover:bg-subtle mx-0 flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${active ? "bg-lagoon-soft font-semibold" : "font-medium"}`}
    >
      <BookOpen className="text-lagoon-strong size-4" />
      <span className="flex flex-col leading-tight">
        Prompt guide
        <span className="text-text-muted text-xs font-normal">What helps, with evidence</span>
      </span>
    </Link>
  )
}

function CostBadge({ projectId }: { projectId: string }) {
  const summary = useCostSummary(projectId).data
  const unknown = (summary?.calls_with_unknown_price ?? 0) > 0
  return (
    <span
      className="text-text-secondary inline-flex items-baseline gap-1.5 text-sm"
      title={unknown ? COMMON_COPY.unknownPriceNote : undefined}
    >
      <span className="hidden sm:inline">{COMMON_COPY.costSpent}</span>
      <span className="text-foreground font-semibold tabular-nums">{formatCost(summary?.cost)}</span>
      {unknown ? <span className="text-warning-strong">+?</span> : null}
    </span>
  )
}

export function ProjectShell({ projectId, children }: { projectId: string; children: ReactNode }) {
  const pathname = usePathname()
  const project = useProject(projectId).data
  const done = useStepCompletion(projectId).data ?? {}
  const [open, setOpen] = useState(false)
  const steps = stepItems(projectId, pathname, done)
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[17.5rem_1fr]">
      <aside className="border-border bg-card sticky top-0 hidden h-screen flex-col gap-7 overflow-y-auto border-r px-3 py-5 lg:flex">
        <Link href="/projects" className="px-3">
          <Logo />
        </Link>
        <Stepper steps={steps} />
        <div className="border-border mt-auto border-t pt-3">
          <ToolLinks projectId={projectId} pathname={pathname} />
        </div>
      </aside>
      {open ? (
        <div className="fixed inset-0 z-30 lg:hidden" role="dialog" aria-modal="true" aria-label="Steps">
          <button
            type="button"
            aria-label="Close menu"
            className="absolute inset-0 bg-[#14203a]/40"
            onClick={() => setOpen(false)}
          />
          <div
            className="bg-card absolute inset-y-0 left-0 flex w-[19rem] max-w-[85vw] flex-col gap-6 overflow-y-auto px-3 py-5 shadow-xl"
            onClick={(event) => {
              if ((event.target as HTMLElement).closest("a")) setOpen(false)
            }}
          >
            <div className="flex items-center justify-between px-3">
              <Logo />
              <Button variant="ghost" size="icon-sm" aria-label="Close menu" onClick={() => setOpen(false)}>
                <X />
              </Button>
            </div>
            <Stepper steps={steps} />
            <div className="border-border border-t pt-3">
              <ToolLinks projectId={projectId} pathname={pathname} />
            </div>
          </div>
        </div>
      ) : null}
      <div className="flex min-w-0 flex-col">
        <header className="border-border bg-card/80 sticky top-0 z-10 flex items-center justify-between gap-3 border-b px-4 py-3 backdrop-blur sm:px-6 lg:px-8">
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <Button
              variant="ghost"
              size="icon-sm"
              className="lg:hidden"
              aria-label="Open menu"
              onClick={() => setOpen(true)}
            >
              <Menu />
            </Button>
            <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-2 text-sm">
              <Link href="/projects" className="text-text-muted hover:text-foreground hidden sm:inline">
                {COMMON_COPY.projects}
              </Link>
              <span className="text-text-muted hidden sm:inline">/</span>
              <h1 className="truncate font-medium">{project?.name ?? COMMON_COPY.loading}</h1>
            </nav>
          </div>
          <div className="flex shrink-0 items-center gap-3 sm:gap-4">
            <CostBadge projectId={projectId} />
            <AccountMenu />
          </div>
        </header>
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">{children}</main>
      </div>
    </div>
  )
}
