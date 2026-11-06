/**
 * The session as a tree: first prompt, then each round's candidates, the winner marked, and under the winner the next
 * round. Every winner shows whether it was proven on held-back cases or is "Not proven". Tests paused at their spending
 * cap are listed with a link to the Run screen, where Resume carries on exactly where they stopped.
 */
"use client"

import Link from "next/link"

import { Section } from "@/components/common/section"
import { StatusBadge } from "@/components/common/status-badge"
import type { CandidateOut, ImprovementOut } from "@/lib/api/types"

const pct = (value: number | null | undefined) => (value == null ? "n/a" : `${Math.round(value * 100)}%`)

function Node({ candidate }: { candidate: CandidateOut }) {
  const tone = candidate.is_winner
    ? candidate.verdict?.reason === "proven"
      ? "success"
      : "warning"
    : candidate.outcome === "rejected"
      ? "danger"
      : "neutral"
  const label = candidate.is_winner
    ? (candidate.label ?? "Waiting for the held-back test")
    : candidate.outcome === "rejected"
      ? "Not tested"
      : candidate.outcome === "pending"
        ? "Testing"
        : "Not chosen"
  const front = candidate.metrics?.front
  return (
    <li className="bg-subtle ring-border flex flex-col gap-1 rounded-lg p-3 text-sm ring-1">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{candidate.strategy}</span>
        <StatusBadge tone={tone}>{label}</StatusBadge>
        {typeof front === "number" ? (
          <span className="text-text-muted text-xs">
            {front === 0 ? "best trade-off" : `trade-off group ${front + 1}`}
          </span>
        ) : null}
      </div>
      <p className="text-text-muted text-xs">
        {candidate.quick_quality != null ? `Quick check ${pct(candidate.quick_quality)} · ` : ""}
        Improving cases {pct(candidate.optimize_quality)}
        {candidate.holdout_quality != null ? ` · Held-back ${pct(candidate.holdout_quality)}` : ""}
      </p>
      {candidate.rejection_reason ? (
        <p className="text-text-muted text-xs">{candidate.rejection_reason}</p>
      ) : null}
    </li>
  )
}

export function SessionTree({ projectId, session }: { projectId: string; session: ImprovementOut }) {
  if (!session.candidates.length) return null
  const rounds = [...new Set(session.candidates.map((c) => c.round))].sort((a, b) => a - b)
  return (
    <Section
      title="Search history"
      description={`Round ${session.current_round} of up to ${session.round_limit}. A round only builds on a winner that was proven on held-back cases.`}
    >
      {session.sizing ? <p className="text-sm">{session.sizing.message}</p> : null}
      {session.paused_experiment_ids.length ? (
        <p className="bg-warning-soft text-warning-strong rounded-lg p-3 text-sm">
          A test stopped at its spending cap.{" "}
          <Link className="underline" href={`/projects/${projectId}/run`}>
            Raise the cap and press Resume on the Run screen
          </Link>
          ; it carries on where it stopped.
        </p>
      ) : null}
      <ol className="flex flex-col gap-4">
        <li className="text-sm font-semibold">First prompt</li>
        {rounds.map((round) => {
          const summary = session.rounds.find((r) => r.round === round)
          return (
            <li key={round} className="border-border ml-3 flex flex-col gap-2 border-l-2 pl-4">
              <div className="flex items-center gap-2 text-sm font-semibold">
                Round {round}
                {summary ? (
                  <StatusBadge tone={summary.proven ? "success" : "warning"}>{summary.label}</StatusBadge>
                ) : null}
              </div>
              <ul className="flex flex-col gap-2">
                {session.candidates
                  .filter((c) => c.round === round)
                  .map((c) => (
                    <Node key={c.id} candidate={c} />
                  ))}
              </ul>
            </li>
          )
        })}
      </ol>
      {session.versus_first ? (
        <p className="text-sm">
          Against the first prompt: <strong>{session.versus_first.message}</strong>
        </p>
      ) : null}
    </Section>
  )
}
