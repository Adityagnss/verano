/**
 * Activity, Guardrails tab: what in Verano stops or refuses spending, and what was refused or
 * failed in this period. Only protections that are really enforced are listed.
 */
"use client"

import { Ban, CircleStop, Gauge, KeyRound, ReceiptText, ShieldCheck } from "lucide-react"

import Link from "next/link"

import type { ActivityOut } from "@/lib/api/types"

import { errorLabel } from "../domain"
import { Panel } from "./parts"

const PROTECTIONS = [
  {
    icon: Gauge,
    name: "Budget cap on each run",
    what: "A run stops before its next model call once it has spent its cap. Set it on the Run step, or as budget in verano.yaml.",
  },
  {
    icon: ReceiptText,
    name: "Cost check before writing test cases",
    what: "Shows the estimate first, and asks you to confirm when it is above the set amount or the price is unknown.",
  },
  {
    icon: CircleStop,
    name: "Stop button",
    what: "Stops a run or a test case generation before its next call. What was already answered is kept.",
  },
  {
    icon: KeyRound,
    name: "Keys checked when added",
    what: "A key the provider refuses is never saved, so a mistyped key is caught before any run.",
  },
  {
    icon: ShieldCheck,
    name: "Provider rate limits respected",
    what: "Calls wait their turn within each provider's limits; a call that waits too long fails as rate limited instead of retrying forever.",
  },
]

export function Guardrails({ data }: { data: ActivityOut | undefined }) {
  const failures = data?.failures ?? []
  const most = Math.max(1, ...failures.map((f) => f.count))
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <Panel title="What stops spending">
        <ul className="flex flex-col">
          {PROTECTIONS.map((p) => (
            <li key={p.name} className="border-border flex gap-3 border-t py-3 first:border-t-0">
              <span className="bg-lagoon-soft text-lagoon-strong flex size-8 shrink-0 items-center justify-center rounded-lg">
                <p.icon className="size-4" aria-hidden />
              </span>
              <span className="flex flex-col gap-0.5">
                <span className="text-sm font-medium">{p.name}</span>
                <span className="text-text-secondary text-sm">{p.what}</span>
              </span>
            </li>
          ))}
        </ul>
        <p className="text-text-muted border-border border-t pt-3 text-xs">
          A monthly spending limit for the whole workspace can be set under{" "}
          <Link href="/workspace" className="underline">
            Workspace, Spending limit
          </Link>
          . Runs stop and say why when it is reached.
        </p>
      </Panel>
      <Panel title="Refused or failed in this period">
        {failures.length ? (
          <ul className="flex flex-col gap-3">
            {failures.map((f) => (
              <li key={f.error_type} className="flex flex-col gap-1">
                <span className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="flex items-center gap-2">
                    <Ban className="text-danger size-3.5 shrink-0" aria-hidden />
                    {errorLabel(f.error_type)}
                  </span>
                  <span className="font-medium tabular-nums">{f.count.toLocaleString()}</span>
                </span>
                <span className="bg-chart-track h-1.5 overflow-hidden rounded-full">
                  <span
                    className="bg-danger/70 block h-full rounded-full"
                    style={{ width: `${(f.count / most) * 100}%` }}
                  />
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-text-muted py-8 text-center text-sm">
            No call was refused or failed in this period.
          </p>
        )}
      </Panel>
    </div>
  )
}
