/** The guided path on the Live traffic page: four steps, each marked done from what exists. */
"use client"

import { Check } from "lucide-react"

import { cn } from "@/lib/utils"

export type ChecklistState = {
  connected: boolean
  hasTraffic: boolean
  caseMade: boolean
  hasAlertRule: boolean
}

const ITEMS = [
  {
    key: "connected",
    title: "Connect your app",
    text: "Create a token and paste three settings into your app.",
  },
  {
    key: "hasTraffic",
    title: "See what arrives",
    text: "Real questions and answers show up in the Traffic tab.",
  },
  {
    key: "caseMade",
    title: "Turn good ones into test cases",
    text: "Pick real questions and add them as drafts to approve.",
  },
  {
    key: "hasAlertRule",
    title: "Get told when quality drops",
    text: "Add an alert rule and say where to send it.",
  },
] as const

export function Checklist({
  state,
  onOpen,
}: {
  state: ChecklistState
  onOpen?: (key: ChecklistKey) => void
}) {
  const firstOpen = ITEMS.find((i) => !state[i.key])?.key
  return (
    <ol aria-label="How to get started" className="flex flex-col gap-0">
      {ITEMS.map((item, index) => {
        const done = state[item.key]
        return (
          <li
            key={item.key}
            className="flex gap-3"
            aria-current={item.key === firstOpen ? "step" : undefined}
          >
            <div className="flex flex-col items-center">
              <span
                className={cn(
                  "flex size-7 shrink-0 items-center justify-center rounded-full border text-xs font-semibold",
                  done
                    ? "border-success-strong bg-success-soft text-success-strong"
                    : item.key === firstOpen
                      ? "border-lagoon-strong bg-lagoon-soft text-lagoon-strong"
                      : "text-text-muted",
                )}
              >
                {done ? <Check className="size-4" aria-hidden /> : index + 1}
              </span>
              {index < ITEMS.length - 1 ? <span className="bg-border w-px flex-1" aria-hidden /> : null}
            </div>
            <div className="min-w-0 pb-4">
              <p className="text-sm font-medium">
                {item.title}
                {done ? <span className="text-success-strong"> (done)</span> : null}
              </p>
              <p className="text-text-secondary text-sm">{item.text}</p>
              {onOpen && !done ? (
                <button
                  type="button"
                  className="text-lagoon-strong min-h-10 text-sm underline sm:min-h-0"
                  onClick={() => onOpen(item.key)}
                >
                  Go to this step
                </button>
              ) : null}
            </div>
          </li>
        )
      })}
    </ol>
  )
}

export type ChecklistKey = (typeof ITEMS)[number]["key"]
