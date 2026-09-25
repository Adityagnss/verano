/**
 * The left-side stepper (DEVELOPMENT.md C1): shows where the user is in the guided path.
 * Completed steps show a check, the current step is highlighted, and steps not built yet
 * are shown as upcoming without a link.
 */
import { Check } from "lucide-react"
import Link from "next/link"

import { cn } from "@/lib/utils"

import { COMMON_COPY } from "./copy"

export type StepState = "done" | "current" | "next" | "upcoming" | "unavailable"
export type StepItem = { key: string; number: number; label: string; href: string; state: StepState }

const MARKER: Record<StepState, string> = {
  done: "bg-success/15 text-success border-success/40",
  current: "bg-primary text-primary-foreground border-primary",
  next: "border-[var(--brand-accent)] text-[var(--brand-accent-soft)]",
  upcoming: "border-border text-muted-foreground",
  unavailable: "border-border text-text-muted",
}

function Marker({ step }: { step: StepItem }) {
  return (
    <span
      className={cn(
        "flex size-6 shrink-0 items-center justify-center rounded-full border text-xs",
        MARKER[step.state],
      )}
    >
      {step.state === "done" ? <Check className="size-3.5" /> : step.number}
    </span>
  )
}

export function Stepper({ steps }: { steps: StepItem[] }) {
  return (
    <nav aria-label="Steps" className="flex flex-col gap-1">
      {steps.map((step) => {
        const body = (
          <>
            <Marker step={step} />
            <span>{step.label}</span>
          </>
        )
        const base = "flex items-center gap-3 rounded-lg px-3 py-2 text-sm"
        return step.state === "unavailable" ? (
          <span
            key={step.key}
            className={cn(base, "text-text-muted cursor-not-allowed")}
            title={COMMON_COPY.upcoming}
          >
            {body}
          </span>
        ) : (
          <Link
            key={step.key}
            href={step.href}
            aria-current={step.state === "current" ? "step" : undefined}
            className={cn(
              base,
              step.state === "current" ? "bg-secondary text-foreground" : "hover:bg-secondary/60",
            )}
          >
            {body}
          </Link>
        )
      })}
    </nav>
  )
}
