/**
 * The left-side stepper, drawn as the loop it is (DEVELOPMENT.md C1, A1): the seven steps
 * are stations on one track, and a return line runs from Improve back to Prompt, because an
 * accepted improvement becomes the prompt's next version and the loop starts again.
 * Done stations show a check, the current one is the single marigold mark on the page, the
 * next open one is named, and steps not built yet aren't links.
 */
import { Check } from "lucide-react"
import Link from "next/link"

import { cn } from "@/lib/utils"

import { COMMON_COPY } from "./copy"

export type StepState = "done" | "current" | "next" | "upcoming" | "unavailable"
export type StepItem = {
  key: string
  number: number
  label: string
  hint: string
  href: string
  state: StepState
}

const ROW = 56
const LOOP_FROM = 1
const LOOP_TO = 6

const MARKER: Record<StepState, string> = {
  done: "bg-success-soft text-success-strong ring-success/40",
  current: "bg-marigold text-foreground ring-marigold-soft ring-4",
  next: "bg-card text-lagoon ring-lagoon",
  upcoming: "bg-card text-text-muted ring-border-strong",
  unavailable: "bg-subtle text-text-muted ring-border",
}

function Marker({ step }: { step: StepItem }) {
  return (
    <span
      className={cn(
        "relative z-[1] flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold tabular-nums ring-1",
        MARKER[step.state],
      )}
    >
      {step.state === "done" ? <Check className="size-3.5" strokeWidth={3} /> : step.number}
    </span>
  )
}

function Loop({ count }: { count: number }) {
  if (count <= LOOP_TO) return null
  return (
    <div
      aria-hidden
      className="border-lagoon/45 pointer-events-none absolute right-2 w-3 rounded-r-lg border-y border-r border-dashed"
      style={{ top: ROW * LOOP_FROM + ROW / 2, height: ROW * (LOOP_TO - LOOP_FROM) }}
    >
      <span className="border-lagoon/70 absolute -top-[4px] -left-[3px] size-2 rotate-45 border-b border-l" />
      <span className="text-lagoon-strong bg-card absolute top-1/2 -right-[7px] -translate-y-1/2 py-1 text-[10px] font-medium [writing-mode:vertical-rl]">
        {COMMON_COPY.loopLabel}
      </span>
    </div>
  )
}

export function Stepper({ steps }: { steps: StepItem[] }) {
  const done = steps.filter((s) => s.state === "done").length
  return (
    <nav aria-label="Steps" className="flex flex-col gap-3">
      <p className="text-text-secondary px-3 text-sm">{COMMON_COPY.stepsDone(done, steps.length)}</p>
      <div className="relative">
        <ol>
          {steps.map((step, index) => {
            const last = index === steps.length - 1
            const body = (
              <>
                <Marker step={step} />
                <span className="flex min-w-0 flex-col pr-6">
                  <span
                    className={cn(
                      "leading-tight",
                      step.state === "current" ? "font-semibold" : "font-medium",
                    )}
                  >
                    {step.label}
                  </span>
                  <span className="text-text-muted truncate text-xs">
                    {step.state === "next"
                      ? `${COMMON_COPY.nextStep}: ${step.hint.toLowerCase()}`
                      : step.hint}
                  </span>
                </span>
              </>
            )
            const base = "relative flex items-center gap-3 rounded-lg px-3 text-sm"
            return (
              <li key={step.key} className="relative" style={{ height: ROW }}>
                {last ? null : (
                  <span
                    aria-hidden
                    className={cn(
                      "absolute left-[25px] w-px",
                      step.state === "done" ? "bg-success/40" : "bg-border-strong",
                    )}
                    style={{ top: ROW / 2 + 14, height: ROW - 28 }}
                  />
                )}
                {step.state === "unavailable" ? (
                  <span
                    className={cn(base, "h-full cursor-not-allowed opacity-60")}
                    title={COMMON_COPY.upcoming}
                  >
                    {body}
                  </span>
                ) : (
                  <Link
                    href={step.href}
                    aria-current={step.state === "current" ? "step" : undefined}
                    className={cn(base, "hover:bg-subtle h-full transition-colors")}
                  >
                    {body}
                  </Link>
                )}
              </li>
            )
          })}
        </ol>
        <Loop count={steps.length} />
      </div>
    </nav>
  )
}
