/** The safety report: per-kind bars with pass rates, failing examples, the CI gate, and Harden. */
"use client"

import Link from "next/link"

import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import type { SecurityReport } from "@/lib/api/types"

import { GATE_MIN_PASS_RATE, pct, rateLevel } from "../domain"

export function ReportView({
  report,
  minPassRate = GATE_MIN_PASS_RATE,
  canHarden,
  hardening,
  hardened,
  onHarden,
  projectId,
  experimentId,
}: {
  report: SecurityReport
  minPassRate?: number
  canHarden: boolean
  hardening: boolean
  hardened: boolean
  onHarden: () => void
  projectId: string
  experimentId: string
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-base font-semibold">
          {pct(report.overall_pass_rate)} of attacks resisted
          {report.experiment_status !== "completed" ? (
            <span className="text-text-muted ml-2 text-sm font-normal">(still running)</span>
          ) : null}
        </p>
        <Button className="min-h-10" disabled={!canHarden || hardening} onClick={onHarden}>
          Harden this prompt
        </Button>
      </div>
      {hardened ? (
        <p role="status" className="text-sm">
          Improve is adding guardrails and will test them on attacks it held back.{" "}
          <Link className="underline" href={`/projects/${projectId}/improve?experiment=${experimentId}`}>
            Follow it on Improve the prompt
          </Link>
          .
        </p>
      ) : null}
      <ul className="flex flex-col gap-2">
        {report.categories.map((c) => {
          const level = rateLevel(c.pass_rate)
          return (
            <li
              key={c.category}
              className="bg-subtle ring-border flex flex-col gap-2 rounded-lg p-3 text-sm ring-1"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{c.title}</span>
                <StatusBadge>OWASP {c.owasp}</StatusBadge>
                <span className="ml-auto flex items-center gap-2">
                  {c.earlier_pass_rate != null ? (
                    <span className="text-text-muted text-xs">before {pct(c.earlier_pass_rate)}</span>
                  ) : null}
                  <span className="font-semibold tabular-nums">{pct(c.pass_rate)}</span>
                  <span className="text-text-secondary text-xs">{level.word}</span>
                </span>
              </div>
              <div
                role="meter"
                aria-label={`${c.title} pass rate`}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round((c.pass_rate ?? 0) * 100)}
                className="bg-border h-2 overflow-hidden rounded-full"
              >
                <div
                  className={`${level.bar} h-full rounded-full`}
                  style={{ width: `${Math.round((c.pass_rate ?? 0) * 100)}%` }}
                />
              </div>
              <p className="text-text-muted text-xs">
                {c.resisted} of {c.answers} answers resisted.
              </p>
              {c.failing_examples.map((x) => (
                <p key={x} className="text-text-muted text-xs break-words">
                  Got through: {x}
                </p>
              ))}
            </li>
          )
        })}
      </ul>
      <p className="text-text-secondary text-sm">
        In CI, <code>verano run --ci --security</code> fails when any kind is below {pct(minPassRate)} or has
        dropped since the last run.
      </p>
      {report.notes.map((n) => (
        <p key={n} className="text-text-muted text-xs">
          {n}
        </p>
      ))}
    </div>
  )
}
