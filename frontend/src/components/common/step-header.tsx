/**
 * The top of every step screen: which step this is, what it is for in one sentence, and
 * how it works as one quiet numbered line (the points are a real sequence), then the
 * "what to fill in, and why" guide, so a first-time user never has to guess what the screen
 * is for. `aside` holds a control such as a picker.
 */
import { BarChart3, Database, KeyRound, ListChecks, PenLine, Play, Sparkles } from "lucide-react"
import type { ReactNode } from "react"

import { STEPS, type StepKey } from "@/lib/steps"

import { UsageGuide } from "./usage-guide"

const ICONS: Record<StepKey, typeof KeyRound> = {
  keys: KeyRound,
  prompt: PenLine,
  data: Database,
  tests: ListChecks,
  run: Play,
  results: BarChart3,
  improve: Sparkles,
}

export function StepHeader({
  step,
  title,
  description,
  howItWorks,
  aside,
  projectId,
}: {
  step: StepKey
  title: string
  description: string
  howItWorks?: string[]
  aside?: ReactNode
  projectId?: string
}) {
  const index = STEPS.findIndex((s) => s.key === step)
  const Icon = ICONS[step]
  return (
    <header className="border-border flex flex-col gap-5 border-b pb-6">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div className="max-w-[52rem] min-w-0">
          <div className="flex items-center gap-3">
            <span className="from-lagoon to-lagoon-strong flex size-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br text-white shadow-sm">
              <Icon className="size-[1.125rem]" />
            </span>
            <div className="flex flex-col gap-1.5">
              <p className="text-lagoon-strong text-xs font-semibold tracking-wide uppercase">
                Step {index + 1} of {STEPS.length}
              </p>
              <div className="flex gap-1" role="presentation">
                {STEPS.map((s, i) => (
                  <span
                    key={s.key}
                    className={`h-1 w-6 rounded-full ${i < index ? "bg-lagoon/50" : i === index ? "bg-lagoon" : "bg-border-strong/60"}`}
                  />
                ))}
              </div>
            </div>
          </div>
          <h2 className="mt-4 text-2xl leading-tight font-semibold sm:text-[1.95rem]">{title}</h2>
          <p className="text-text-secondary mt-2 text-[0.95rem] leading-relaxed">{description}</p>
        </div>
        {aside}
      </div>
      {howItWorks?.length ? (
        <ol className="text-text-secondary grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2 xl:grid-cols-4">
          {howItWorks.map((point, i) => (
            <li key={point} className="flex gap-2 leading-snug">
              <span className="text-lagoon font-semibold tabular-nums">{i + 1}</span>
              <span>{point}</span>
            </li>
          ))}
        </ol>
      ) : null}
      <UsageGuide step={step} projectId={projectId} />
    </header>
  )
}
