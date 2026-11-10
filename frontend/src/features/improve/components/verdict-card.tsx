/** The verdict in plain words: Proven better, Not proven or Worse, with the held-back numbers behind it. */
import { CircleAlert, CircleCheck, CircleX } from "lucide-react"
import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

import { IMPROVE_COPY } from "../copy"

export type VerdictKind = "better" | "worse" | "not_proven"

/** Maps the server's reason to one of the three words a person needs. */
export function verdictKind(reason: string): VerdictKind {
  if (reason === "proven") return "better"
  if (reason === "worse") return "worse"
  return "not_proven"
}

const LOOK: Record<VerdictKind, { box: string; Icon: typeof CircleCheck }> = {
  better: { box: "bg-success-soft text-success-strong ring-success/25", Icon: CircleCheck },
  worse: { box: "bg-danger-soft text-danger-strong ring-danger/20", Icon: CircleX },
  not_proven: { box: "bg-warning-soft text-warning-strong ring-warning/25", Icon: CircleAlert },
}

const pct = (value: number | null | undefined) => (value == null ? "n/a" : `${Math.round(value * 100)}%`)

type Props = {
  reason: string
  before: number | null | undefined
  after: number | null | undefined
  children?: ReactNode
}

export function VerdictCard({ reason, before, after, children }: Props) {
  const kind = verdictKind(reason)
  const { box, Icon } = LOOK[kind]
  return (
    <div className={cn("flex flex-col gap-2 rounded-xl p-4 ring-1", box)} data-testid="verdict-card">
      <div className="flex items-start gap-3">
        <Icon className="mt-0.5 size-5 shrink-0" aria-hidden />
        <div className="min-w-0">
          <p className="text-base font-semibold">{IMPROVE_COPY.verdict[kind]}</p>
          <p className="text-sm">{IMPROVE_COPY.verdictNumbers(pct(before), pct(after))}</p>
        </div>
      </div>
      {children}
    </div>
  )
}
