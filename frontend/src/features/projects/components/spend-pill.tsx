/**
 * The spend pill in the header. Inside a project it shows what the project has spent on models
 * so far (with "+?" when some calls had an unknown price); outside a project it is a plain link
 * to Usage and spend. Either way it opens Usage and spend.
 */
"use client"

import { Wallet } from "lucide-react"
import Link from "next/link"

import { COMMON_COPY } from "@/components/common/copy"
import { formatCost } from "@/lib/format"

import { useCostSummary } from "../hooks"

const PILL =
  "ring-border bg-card hover:bg-subtle focus-visible:ring-ring inline-flex h-10 items-center gap-1.5 rounded-full px-3 text-sm ring-1 focus-visible:ring-2 focus-visible:outline-none"

function ProjectCost({ projectId }: { projectId: string }) {
  const summary = useCostSummary(projectId).data
  const unknown = (summary?.calls_with_unknown_price ?? 0) > 0
  return (
    <Link
      href="/activity"
      className={PILL}
      aria-label={`Spent on models in this project: ${formatCost(summary?.cost)}. Open usage and spend.`}
      title={unknown ? COMMON_COPY.unknownPriceNote : COMMON_COPY.costSpent}
    >
      <Wallet aria-hidden className="text-text-muted size-4" />
      <span className="font-semibold tabular-nums">{formatCost(summary?.cost)}</span>
      {unknown ? <span className="text-warning-strong">+?</span> : null}
    </Link>
  )
}

export function SpendPill({ projectId }: { projectId?: string }) {
  if (projectId) return <ProjectCost projectId={projectId} />
  return (
    <Link href="/activity" className={PILL} aria-label="Usage and spend">
      <Wallet aria-hidden className="text-text-muted size-4" />
      <span className="hidden sm:inline">Spend</span>
    </Link>
  )
}
