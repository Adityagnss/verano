/** Says what "clearly better" and "proven" mean, with the two numbers this server uses. */
"use client"

import { CircleHelp } from "lucide-react"

import { useEvidenceThresholds } from "@/features/checks/hooks"

import { PROOF_COPY } from "../screens-copy"

export function ProofExplainer({ projectId }: { projectId: string }) {
  const numbers = useEvidenceThresholds(projectId)
  return (
    <details className="bg-subtle ring-border rounded-xl p-4 text-sm ring-1">
      <summary className="flex cursor-pointer items-center gap-2 font-semibold">
        <CircleHelp className="text-lagoon size-4" />
        {PROOF_COPY.heading}
      </summary>
      <div className="text-text-secondary mt-2 flex flex-col gap-2">
        {numbers.data ? (
          <>
            <p>{PROOF_COPY.clearly(numbers.data.clearly_better_min_cases)}</p>
            <p>{PROOF_COPY.proven(numbers.data.proven_min_holdout)}</p>
            <p>{PROOF_COPY.difference}</p>
          </>
        ) : (
          <p>{numbers.error ? PROOF_COPY.difference : PROOF_COPY.fallback}</p>
        )}
      </div>
    </details>
  )
}
