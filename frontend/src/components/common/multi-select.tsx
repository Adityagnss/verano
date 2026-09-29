/**
 * A filter dropdown with a checkbox per option (pick several). The button shows the label and
 * how many are chosen; it closes when you click elsewhere or press Escape.
 */
"use client"

import { Check, ChevronDown } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { cn } from "@/lib/utils"

export type Choice = { value: string; label: string; hint?: string }

export function MultiSelect({
  label,
  choices,
  value,
  onChange,
  empty = "Nothing to choose yet",
}: {
  label: string
  choices: Choice[]
  value: string[]
  onChange: (value: string[]) => void
  empty?: string
}) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false)
    }
    const escape = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false)
    document.addEventListener("mousedown", close)
    document.addEventListener("keydown", escape)
    return () => {
      document.removeEventListener("mousedown", close)
      document.removeEventListener("keydown", escape)
    }
  }, [open])
  const toggle = (item: string) =>
    onChange(value.includes(item) ? value.filter((v) => v !== item) : [...value, item])
  return (
    <div ref={box} className="relative">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className={cn(
          "bg-card ring-border hover:ring-border-strong flex h-9 items-center gap-2 rounded-lg px-3 text-sm ring-1 transition-shadow",
          value.length > 0 && "ring-lagoon/50 bg-lagoon-soft/60",
        )}
      >
        <span className="font-medium">{label}</span>
        {value.length > 0 ? (
          <span className="bg-lagoon text-primary-foreground rounded-full px-1.5 text-xs tabular-nums">
            {value.length}
          </span>
        ) : null}
        <ChevronDown className="text-text-muted size-4" />
      </button>
      {open ? (
        <div
          role="listbox"
          aria-multiselectable
          aria-label={label}
          className="bg-card ring-border shadow-float absolute top-full left-0 z-30 mt-1 flex max-h-72 min-w-56 flex-col overflow-y-auto rounded-xl p-1 ring-1"
        >
          {choices.length === 0 ? <p className="text-text-muted px-3 py-2 text-sm">{empty}</p> : null}
          {choices.map((choice) => {
            const chosen = value.includes(choice.value)
            return (
              <button
                key={choice.value}
                type="button"
                role="option"
                aria-selected={chosen}
                onClick={() => toggle(choice.value)}
                className="hover:bg-subtle flex items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm"
              >
                <span
                  className={cn(
                    "flex size-4 shrink-0 items-center justify-center rounded border",
                    chosen ? "bg-lagoon border-lagoon text-primary-foreground" : "border-border-strong",
                  )}
                >
                  {chosen ? <Check className="size-3" strokeWidth={3} /> : null}
                </span>
                <span className="flex min-w-0 flex-col">
                  <span className="truncate">{choice.label}</span>
                  {choice.hint ? (
                    <span className="text-text-muted truncate text-xs">{choice.hint}</span>
                  ) : null}
                </span>
              </button>
            )
          })}
          {value.length > 0 ? (
            <button
              type="button"
              onClick={() => onChange([])}
              className="text-lagoon-strong border-border mt-1 border-t px-3 py-2 text-left text-xs font-medium"
            >
              Clear {label.toLowerCase()}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
