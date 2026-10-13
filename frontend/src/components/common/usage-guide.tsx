/**
 * "What to fill and why" under a step's title: every field or choice on the screen, what to
 * put in it, why Verano asks, and an example. Open the first time a step is seen, folded from
 * then on, and it stays as the user left it (remembered in this browser only). Always one click away.
 */
"use client"

import { BookOpen, ChevronDown, Lightbulb } from "lucide-react"
import Link from "next/link"
import { useEffect, useState } from "react"

import { STEP_GUIDES } from "@/lib/guide"
import type { StepKey } from "@/lib/steps"
import { cn } from "@/lib/utils"

const KEY = (step: StepKey) => `verano.guide.${step}`

function remembered(step: StepKey): boolean | null {
  try {
    const value = window.localStorage.getItem(KEY(step))
    return value === null ? null : value === "open"
  } catch {
    return null
  }
}

export function UsageGuide({ step, projectId }: { step: StepKey; projectId?: string }) {
  const guide = STEP_GUIDES[step]
  const [open, setOpen] = useState(true)
  useEffect(() => {
    const saved = remembered(step)
    // eslint-disable-next-line react-hooks/set-state-in-effect -- read the saved choice after mount, so server and client render alike
    if (saved !== null) setOpen(saved)
    else {
      // first visit: shown now, folded away from the next visit on
      try {
        window.localStorage.setItem(KEY(step), "closed")
      } catch {
        /* private mode: it just stays open */
      }
    }
  }, [step])
  function toggle() {
    const next = !open
    setOpen(next)
    try {
      window.localStorage.setItem(KEY(step), next ? "open" : "closed")
    } catch {
      /* private mode: the choice just isn't remembered */
    }
  }
  return (
    <section className="bg-lagoon-soft/50 ring-lagoon/15 rounded-xl ring-1" aria-label="How to use this step">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm font-medium"
      >
        <BookOpen className="text-lagoon-strong size-4 shrink-0" />
        <span className="text-lagoon-strong">What to fill in, and why</span>
        <ChevronDown
          className={cn(
            "text-lagoon-strong ml-auto size-4 shrink-0 transition-transform",
            open && "rotate-180",
          )}
        />
      </button>
      {open ? (
        <div className="flex flex-col gap-4 px-4 pb-4">
          <p className="text-text-secondary max-w-[60rem] text-sm leading-relaxed">{guide.intro}</p>
          <dl className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {guide.fields.map((field) => (
              <div
                key={field.name}
                className="bg-card ring-border flex flex-col gap-1.5 rounded-lg p-3 ring-1"
              >
                <dt className="text-sm font-semibold">{field.name}</dt>
                <dd className="flex flex-col gap-1.5 text-[0.8125rem] leading-snug">
                  <p>
                    <span className="text-lagoon-strong font-medium">Put: </span>
                    {field.put}
                  </p>
                  <p className="text-text-secondary">
                    <span className="text-lagoon-strong font-medium">Why: </span>
                    {field.why}
                  </p>
                  {field.example ? (
                    <p className="bg-subtle text-text-secondary rounded-md px-2 py-1 font-mono text-xs break-words whitespace-pre-wrap">
                      {field.example}
                    </p>
                  ) : null}
                </dd>
              </div>
            ))}
          </dl>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
            {guide.tip ? (
              <p className="text-text-secondary flex items-start gap-2">
                <Lightbulb className="text-lagoon-strong mt-0.5 size-4 shrink-0" />
                {guide.tip}
              </p>
            ) : null}
            {projectId && (step === "prompt" || step === "improve") ? (
              <Link
                href={`/projects/${projectId}/guide`}
                className="text-lagoon-strong font-medium hover:underline"
              >
                Read the prompt guide →
              </Link>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  )
}
