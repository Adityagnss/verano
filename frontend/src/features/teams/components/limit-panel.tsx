/** Guardrails: the workspace's monthly spending limit. Runs stop, and say why, when it is reached. */
"use client"

import { useState } from "react"
import { toast } from "sonner"

import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { MembershipRole } from "@/lib/api/types"

import { atLeast, money } from "../domain"
import { useGuardrails, useSetLimit } from "../hooks"

export function LimitPanel({ organizationId, role }: { organizationId: string; role: MembershipRole }) {
  const guardrails = useGuardrails(organizationId)
  const save = useSetLimit(organizationId)
  const [value, setValue] = useState<string | null>(null)
  const data = guardrails.data
  const shown = value ?? (data?.monthly_spend_limit ? String(Number(data.monthly_spend_limit)) : "")
  const manage = atLeast(role, "admin")

  async function submit(limit: number | null) {
    await save.mutateAsync(limit)
    setValue(null)
    toast.success(limit === null ? "Spending limit removed." : "Spending limit saved.")
  }

  return (
    <div className="flex max-w-xl flex-col gap-4">
      <p className="text-text-secondary text-sm">
        A monthly limit for everything this workspace spends on models. Before each call, and between batches
        of a run, Verano checks it. When it is reached, runs stop (finished answers are kept) and say why.
      </p>
      <ErrorMessage error={guardrails.error ?? save.error} />
      {data ? (
        <p className="text-sm">
          Spent this month: <strong>{money(data.spent_this_month)}</strong>
          {data.monthly_spend_limit
            ? ` of ${money(data.monthly_spend_limit)} (${data.percent_used}%)`
            : " (no limit set)"}
          {data.limit_reached ? <span className="text-danger"> The limit is reached.</span> : null}
        </p>
      ) : null}
      {manage ? (
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            void submit(Number(shown)).catch(() => undefined)
          }}
        >
          <span className="text-sm">$</span>
          <Input
            type="number"
            min="0.01"
            step="0.01"
            required
            aria-label="Monthly limit in dollars"
            value={shown}
            onChange={(e) => setValue(e.target.value)}
            className="w-40"
          />
          <Button type="submit" disabled={save.isPending}>
            Save limit
          </Button>
          {data?.monthly_spend_limit ? (
            <Button type="button" variant="ghost" onClick={() => void submit(null).catch(() => undefined)}>
              Remove limit
            </Button>
          ) : null}
        </form>
      ) : (
        <p className="text-text-muted text-sm">Only owners and admins can change the limit.</p>
      )}
    </div>
  )
}
