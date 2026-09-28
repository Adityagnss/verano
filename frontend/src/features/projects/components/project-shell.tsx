/**
 * The frame around every project step (DEVELOPMENT.md C3): logo and stepper on the left,
 * a breadcrumb with the project name and the project's running LLM cost at the top, the
 * step's content below.
 * When some calls used models with an unknown price, the cost says so instead of looking
 * complete.
 */
"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import type { ReactNode } from "react"

import { COMMON_COPY } from "@/components/common/copy"
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

function CostBadge({ projectId }: { projectId: string }) {
  const summary = useCostSummary(projectId).data
  const unknown = (summary?.calls_with_unknown_price ?? 0) > 0
  return (
    <span
      className="text-text-secondary inline-flex items-baseline gap-1.5 text-sm"
      title={unknown ? COMMON_COPY.unknownPriceNote : undefined}
    >
      {COMMON_COPY.costSpent}
      <span className="text-foreground font-semibold tabular-nums">{formatCost(summary?.cost)}</span>
      {unknown ? <span className="text-warning-strong">+?</span> : null}
    </span>
  )
}

export function ProjectShell({ projectId, children }: { projectId: string; children: ReactNode }) {
  const pathname = usePathname()
  const project = useProject(projectId).data
  const done = useStepCompletion(projectId).data ?? {}
  return (
    <div className="grid min-h-screen grid-cols-[17.5rem_1fr]">
      <aside className="border-border bg-card sticky top-0 flex h-screen flex-col gap-7 border-r px-3 py-5">
        <Link href="/projects" className="px-3">
          <Logo />
        </Link>
        <Stepper steps={stepItems(projectId, pathname, done)} />
      </aside>
      <div className="flex min-w-0 flex-col">
        <header className="border-border bg-card/80 sticky top-0 z-10 flex items-center justify-between border-b px-8 py-3 backdrop-blur">
          <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-2 text-sm">
            <Link href="/projects" className="text-text-muted hover:text-foreground">
              {COMMON_COPY.projects}
            </Link>
            <span className="text-text-muted">/</span>
            <h1 className="truncate font-medium">{project?.name ?? COMMON_COPY.loading}</h1>
          </nav>
          <div className="flex items-center gap-4">
            <CostBadge projectId={projectId} />
            <AccountMenu />
          </div>
        </header>
        <main className="flex-1 px-10 py-8">{children}</main>
      </div>
    </div>
  )
}
