/**
 * "Why this score": for each check that scored an answer, its reason, how many answers it rests on, what it cannot
 * tell, and (for a judge) how often it agrees with people. Loaded only when opened.
 */
"use client"

import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"

import { EVIDENCE_COPY } from "../copy"
import { useEvidence } from "../hooks"

export function EvidencePanel({
  projectId,
  experimentId,
  answerId,
}: {
  projectId: string
  experimentId: string
  answerId: string
}) {
  const [open, setOpen] = useState(false)
  const evidence = useEvidence(projectId, experimentId, answerId, open)
  return (
    <div className="mt-2 flex flex-col gap-2">
      <Button variant="ghost" size="sm" className="self-start" onClick={() => setOpen((v) => !v)}>
        {open ? EVIDENCE_COPY.close : EVIDENCE_COPY.open}
      </Button>
      {open && evidence.error ? <ErrorMessage error={evidence.error} /> : null}
      {open && evidence.data ? (
        <ul className="flex flex-col gap-3">
          {evidence.data.scores.map((s) => (
            <li
              key={s.evaluator_name}
              className="bg-subtle ring-border flex flex-col gap-1 rounded-lg p-3 text-xs ring-1"
            >
              <p className="font-medium">
                {s.evaluator_name.replaceAll("_", " ")}{" "}
                <span className="text-text-muted font-normal">· {EVIDENCE_COPY.kind[s.kind] ?? s.kind}</span>
              </p>
              <p>{s.reason}</p>
              <p className="text-text-secondary">
                {EVIDENCE_COPY.basis(s.answers_scored, s.answers_unscored)}
              </p>
              {s.cached ? <p className="text-text-secondary">{EVIDENCE_COPY.cached}</p> : null}
              <p className="text-text-secondary">
                <span className="font-medium">{EVIDENCE_COPY.cannot}:</span> {s.limits}
              </p>
              {s.agreement ? (
                <p className={s.agreement.warn ? "text-warning-strong" : "text-text-secondary"}>
                  {s.agreement.message}
                </p>
              ) : s.agreement_note ? (
                <p className="text-text-muted">{s.agreement_note}</p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
