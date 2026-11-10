/**
 * `Wizard`: a stepped flow, one decision per screen. A progress indicator (named dots on wide
 * screens, "Step 2 of 4" plus a bar on phones), Back / Next buttons, a per-step `validate` hook
 * that can block Next with a message, and a short slide-and-fade between steps (skipped under
 * reduced motion). Step content is rendered only while its step is current.
 *
 *   <Wizard
 *     steps={[
 *       { id: "name", title: "Name it", content: <NameField />, validate: () => name ? true : "Enter a name." },
 *       { id: "confirm", title: "Confirm", content: <Summary /> },
 *     ]}
 *     finishLabel="Create project"
 *     onFinish={async () => { await save() }}
 *     onCancel={() => router.back()}
 *   />
 *
 * `validate` may return `true`, or a string (the problem, shown under the step), and may be async.
 * Set `step` and `onStepChange` to control the position yourself.
 */
"use client"

import { Check } from "lucide-react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { type ReactNode, useState } from "react"

import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { cn } from "@/lib/utils"

export type WizardStep = {
  id: string
  title: string
  description?: string
  content: ReactNode
  /** Return true to continue, or a message explaining what to fix. */
  validate?: () => true | string | Promise<true | string>
  /** Label of the Next button on this step; defaults to "Next". */
  nextLabel?: string
}

export type WizardProps = {
  steps: WizardStep[]
  onFinish: () => void | Promise<void>
  finishLabel?: string
  /** Shows a "Cancel" button on the first step. */
  onCancel?: () => void
  /** Controlled position (index). */
  step?: number
  onStepChange?: (index: number) => void
  className?: string
}

export function Wizard({
  steps,
  onFinish,
  finishLabel = "Finish",
  onCancel,
  step: stepProp,
  onStepChange,
  className,
}: WizardProps) {
  const [inner, setInner] = useState(0)
  const [direction, setDirection] = useState(1)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const reduced = useReducedMotion()

  const index = Math.min(stepProp ?? inner, steps.length - 1)
  const current = steps[index]
  const last = index === steps.length - 1

  function go(next: number) {
    setDirection(next > index ? 1 : -1)
    setError(null)
    if (onStepChange) onStepChange(next)
    if (stepProp === undefined) setInner(next)
  }

  async function forward() {
    setBusy(true)
    try {
      const result = current.validate ? await current.validate() : true
      if (result !== true) {
        setError(result)
        return
      }
      if (last) await onFinish()
      else go(index + 1)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong. Try again.")
    } finally {
      setBusy(false)
    }
  }

  const offset = reduced ? 0 : 16 * direction
  return (
    <section aria-label="Guided steps" className={cn("flex flex-col gap-6", className)}>
      <nav aria-label="Progress" className="flex flex-col gap-2">
        <p className="text-text-secondary text-sm sm:hidden" aria-live="polite">
          Step {index + 1} of {steps.length}:{" "}
          <span className="text-foreground font-medium">{current.title}</span>
        </p>
        <Progress value={((index + 1) / steps.length) * 100} aria-label="Progress" className="sm:hidden" />
        <ol className="hidden items-center gap-2 sm:flex">
          {steps.map((entry, position) => {
            const done = position < index
            return (
              <li key={entry.id} className="flex min-w-0 flex-1 items-center gap-2 last:flex-none">
                <span
                  aria-current={position === index ? "step" : undefined}
                  className={cn(
                    "flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold tabular-nums ring-1",
                    done && "bg-success-soft text-success-strong ring-success/40",
                    position === index && "bg-primary text-primary-foreground ring-primary",
                    position > index && "bg-card text-text-muted ring-border-strong",
                  )}
                >
                  {done ? <Check className="size-3.5" strokeWidth={3} aria-label="Done" /> : position + 1}
                </span>
                <span
                  className={cn(
                    "truncate text-sm",
                    position === index ? "text-foreground font-medium" : "text-text-secondary",
                  )}
                >
                  {entry.title}
                </span>
                {position < steps.length - 1 ? (
                  <span
                    aria-hidden
                    className={cn("h-px flex-1", done ? "bg-success/40" : "bg-border-strong")}
                  />
                ) : null}
              </li>
            )
          })}
        </ol>
      </nav>
      <div className="min-h-[8rem]">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={current.id}
            initial={{ opacity: 0, x: offset }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -offset }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="flex flex-col gap-4"
          >
            <div>
              <h2 className="text-lg font-semibold">{current.title}</h2>
              {current.description ? (
                <p className="text-text-secondary mt-1 text-sm">{current.description}</p>
              ) : null}
            </div>
            {current.content}
          </motion.div>
        </AnimatePresence>
        {error ? (
          <p role="alert" className="text-danger-strong mt-3 text-sm">
            {error}
          </p>
        ) : null}
      </div>
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          {index > 0 ? (
            <Button
              variant="ghost"
              size="lg"
              className="min-h-10 w-full sm:w-auto"
              onClick={() => go(index - 1)}
              disabled={busy}
            >
              Back
            </Button>
          ) : onCancel ? (
            <Button variant="ghost" size="lg" className="min-h-10 w-full sm:w-auto" onClick={onCancel}>
              Cancel
            </Button>
          ) : null}
        </div>
        <Button
          size="lg"
          className="min-h-10 w-full sm:w-auto"
          onClick={() => void forward()}
          disabled={busy}
        >
          {last ? finishLabel : (current.nextLabel ?? "Next")}
        </Button>
      </div>
    </section>
  )
}
