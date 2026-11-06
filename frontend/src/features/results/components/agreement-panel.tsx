/**
 * Does the judge agree with people? One row per judged check: how many labelled answers were compared, the share
 * that match and Cohen's kappa, with the warning from the server when the judge should not be relied on.
 */
"use client"

import { CircleAlert, CircleCheck } from "lucide-react"

import { Section } from "@/components/common/section"
import { StatusBadge } from "@/components/common/status-badge"

import { AGREEMENT_COPY } from "../copy"
import { useAgreement } from "../hooks"

export function AgreementPanel({ projectId, experimentId }: { projectId: string; experimentId: string }) {
  const agreement = useAgreement(projectId, experimentId)
  const rows = agreement.data ?? []
  return (
    <Section title={AGREEMENT_COPY.title} description={AGREEMENT_COPY.description}>
      {rows.length === 0 ? (
        <p className="text-text-muted text-sm">{AGREEMENT_COPY.empty}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {rows.map((row) => (
            <li
              key={row.evaluator_name}
              className="border-border flex flex-col gap-1 rounded-lg border p-3 text-sm"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{row.evaluator_name.replaceAll("_", " ")}</span>
                <StatusBadge
                  tone={row.too_few ? "neutral" : row.warn ? "warning" : "success"}
                  icon={row.warn ? <CircleAlert /> : <CircleCheck />}
                >
                  {row.too_few ? "too few labels" : row.warn ? "low agreement" : "agrees"}
                </StatusBadge>
                <span className="text-text-secondary ml-auto text-xs tabular-nums">
                  {AGREEMENT_COPY.agree} {row.raw === null ? "–" : `${Math.round(row.raw * 100)}%`} ·{" "}
                  {AGREEMENT_COPY.kappa} {row.kappa === null ? "–" : row.kappa.toFixed(2)}
                </span>
              </div>
              <p className="text-text-secondary text-xs">{row.message}</p>
              <p className="text-text-muted text-xs">
                {AGREEMENT_COPY.used(row.answers_used, row.labelled_answers)}
                {row.unsure_or_disputed ? ` · ${AGREEMENT_COPY.skipped(row.unsure_or_disputed)}` : ""}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}
