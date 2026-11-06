/** The judge gallery: ready-made judged checks with what they cannot tell and how often they agree with people. */
"use client"

import { Skeleton } from "@/components/ui/skeleton"
import { ErrorMessage } from "@/components/common/error-message"
import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import type { EvaluatorSetVersionOut } from "@/lib/api/types"

import { CHECKS_COPY } from "../copy"
import { hasCheck, requirementText } from "../domain"
import { useJudgeGallery } from "../hooks"
import type { AddCheck } from "./check-library"

const COPY = CHECKS_COPY.judges

export function JudgeGallery({
  projectId,
  set,
  frozen,
  busy,
  add,
}: {
  projectId: string
  set: EvaluatorSetVersionOut
  frozen: boolean
  busy: boolean
  add: AddCheck
}) {
  const gallery = useJudgeGallery(projectId)
  if (gallery.isPending)
    return (
      <div className="grid gap-3 md:grid-cols-2" aria-label={CHECKS_COPY.loading}>
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
      </div>
    )
  if (gallery.error) return <ErrorMessage error={gallery.error} />
  if (gallery.data.length === 0) return <p className="text-text-muted text-sm">{COPY.empty}</p>
  return (
    <div className="flex flex-col gap-3">
      <p className="text-text-secondary text-sm">{COPY.intro}</p>
      <ul className="grid gap-3 md:grid-cols-2">
        {gallery.data.map((judge) => {
          const present = hasCheck(set, judge.id)
          const needs = requirementText(judge.requires)
          return (
            <li key={judge.id} className="bg-subtle ring-border flex flex-col gap-2 rounded-lg p-3 ring-1">
              <div className="flex flex-wrap items-center gap-2">
                <h4 className="text-sm font-semibold">{judge.title}</h4>
                {judge.agreement ? (
                  <StatusBadge tone="success">Measured</StatusBadge>
                ) : (
                  <StatusBadge tone="warning">{COPY.notMeasured}</StatusBadge>
                )}
              </div>
              <p className="text-sm">{judge.description}</p>
              <p className="text-text-secondary text-xs">
                {judge.agreement
                  ? COPY.measured(
                      judge.agreement.kappa,
                      judge.agreement.raw,
                      judge.agreement.answers,
                      judge.agreement.model,
                    )
                  : (judge.agreement_note ?? COPY.notMeasured)}
              </p>
              <p className="text-text-secondary text-xs">
                <span className="font-medium">{COPY.cannot}: </span>
                {judge.limits}
              </p>
              {needs ? <p className="text-text-secondary text-xs">{COPY.needs(needs)}</p> : null}
              <p className="text-text-secondary text-xs">{COPY.passMark(judge.threshold)}</p>
              <details className="text-xs">
                <summary className="text-text-muted cursor-pointer">{COPY.instruction}</summary>
                <p className="mt-1 whitespace-pre-wrap">{judge.criteria}</p>
              </details>
              <div className="mt-auto pt-1">
                {present ? (
                  <StatusBadge tone="info">{CHECKS_COPY.already}</StatusBadge>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={frozen || busy}
                    onClick={() =>
                      void add(
                        {
                          evaluator_name: judge.id,
                          evaluator_version: "1",
                          config: judge.config as Record<string, unknown>,
                          threshold: judge.threshold,
                          weight: 1,
                          required: false,
                        },
                        judge.title,
                      )
                    }
                  >
                    {busy ? CHECKS_COPY.adding : CHECKS_COPY.add}
                  </Button>
                )}
              </div>
            </li>
          )
        })}
      </ul>
      <p className="text-text-muted text-xs">{COPY.needsJudge}</p>
    </div>
  )
}
