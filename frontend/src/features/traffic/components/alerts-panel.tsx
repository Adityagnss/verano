/** Alerts: where to send them, the rules, and the alerts raised so far. */
"use client"

import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { Section } from "@/components/common/section"
import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

import { TRAFFIC_COPY as C } from "../copy"
import { percent } from "../domain"
import {
  useAddChannel,
  useAddRule,
  useAlerts,
  useChannels,
  useDeleteChannel,
  useDeleteRule,
  useEvaluateAlerts,
  useResolveAlert,
  useRules,
  useStats,
  useTestChannel,
} from "../hooks"
import type { ChannelCreate } from "../types"

const SELECT = "border-input bg-background h-9 rounded-lg border px-3 text-sm"

function Channels({ projectId }: { projectId: string }) {
  const channels = useChannels(projectId)
  const add = useAddChannel(projectId)
  const test = useTestChannel(projectId)
  const remove = useDeleteChannel(projectId)
  const stats = useStats(projectId)
  const [kind, setKind] = useState<ChannelCreate["kind"]>("slack")
  const [name, setName] = useState("")
  const [target, setTarget] = useState("")
  const emailOn = stats.data?.email_available ?? false
  return (
    <Section title={C.alerts.channels}>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault()
          add.mutate(
            { kind, name: name.trim(), target: target.trim() },
            {
              onSuccess: () => {
                setName("")
                setTarget("")
              },
            },
          )
        }}
      >
        <select
          aria-label="Kind"
          className={SELECT}
          value={kind}
          onChange={(e) => setKind(e.target.value as ChannelCreate["kind"])}
        >
          <option value="slack">Slack</option>
          <option value="webhook">Webhook</option>
          {emailOn ? <option value="email">Email</option> : null}
        </select>
        <Input
          aria-label="Name"
          placeholder="Name"
          className="max-w-40"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <Input
          aria-label="Address"
          placeholder={kind === "email" ? "team@example.com" : "https://…"}
          className="min-w-60 flex-1"
          type={kind === "email" ? "text" : "password"}
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          required
        />
        <Button type="submit" disabled={add.isPending}>
          {C.alerts.addChannel}
        </Button>
      </form>
      {emailOn ? null : <p className="text-text-muted text-xs">{C.alerts.emailOff}</p>}
      <ErrorMessage error={add.error ?? test.error ?? remove.error} />
      {test.data ? (
        <p className="text-sm" role="status">
          {test.data.message}
        </p>
      ) : null}
      <ul className="divide-border flex flex-col divide-y">
        {(channels.data ?? []).map((c) => (
          <li key={c.id} className="flex flex-wrap items-center justify-between gap-3 py-2 text-sm">
            <span>
              {c.name} <StatusBadge>{c.kind}</StatusBadge>{" "}
              <span className="text-text-muted">{c.target_hint}</span>
              {c.last_error ? <span className="text-danger-strong"> — {c.last_error}</span> : null}
            </span>
            <span className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => test.mutate(c.id)}>
                {C.alerts.test}
              </Button>
              <Button size="sm" variant="outline" onClick={() => remove.mutate(c.id)}>
                Remove
              </Button>
            </span>
          </li>
        ))}
      </ul>
    </Section>
  )
}

function Rules({ projectId }: { projectId: string }) {
  const rules = useRules(projectId)
  const channels = useChannels(projectId)
  const add = useAddRule(projectId)
  const remove = useDeleteRule(projectId)
  const [name, setName] = useState("")
  const [kind, setKind] = useState<"drop" | "threshold">("drop")
  const [level, setLevel] = useState(0.8)
  const [margin, setMargin] = useState(0.1)
  const [chosen, setChosen] = useState<string[]>([])
  const [quiet, setQuiet] = useState({ start: "", end: "" })
  return (
    <Section title={C.alerts.rules}>
      <form
        className="grid gap-3 sm:grid-cols-2"
        onSubmit={(event) => {
          event.preventDefault()
          const hasQuiet = quiet.start !== "" && quiet.end !== ""
          add.mutate(
            {
              name: name.trim(),
              kind,
              metric: "pass_rate",
              window_days: 3,
              baseline_days: 14,
              min_samples: 30,
              min_bad_days: 2,
              quiet_utc_offset_min: 0,
              enabled: true,
              threshold: level,
              margin,
              channel_ids: chosen,
              quiet_start_hour: hasQuiet ? Number(quiet.start) : null,
              quiet_end_hour: hasQuiet ? Number(quiet.end) : null,
            },
            { onSuccess: () => setName("") },
          )
        }}
      >
        <Input
          aria-label="Rule name"
          placeholder="Rule name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <select
          aria-label="Kind of rule"
          className={SELECT}
          value={kind}
          onChange={(e) => setKind(e.target.value as "drop" | "threshold")}
        >
          <option value="drop">Alert when the pass rate falls below its usual level</option>
          <option value="threshold">Alert when the pass rate falls below a fixed level</option>
        </select>
        {kind === "threshold" ? (
          <label className="flex flex-col gap-1.5 text-sm">
            Fixed level (0 to 1)
            <Input
              type="number"
              step="0.05"
              min={0.05}
              max={0.95}
              value={level}
              onChange={(e) => setLevel(Number(e.target.value))}
            />
          </label>
        ) : null}
        <label className="flex flex-col gap-1.5 text-sm">
          How far below counts (0 to 0.5)
          <Input
            type="number"
            step="0.05"
            min={0.05}
            max={0.45}
            value={margin}
            onChange={(e) => setMargin(Number(e.target.value))}
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          Quiet hours start (UTC hour, optional)
          <Input
            type="number"
            min={0}
            max={23}
            value={quiet.start}
            onChange={(e) => setQuiet((q) => ({ ...q, start: e.target.value }))}
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          Quiet hours end
          <Input
            type="number"
            min={0}
            max={23}
            value={quiet.end}
            onChange={(e) => setQuiet((q) => ({ ...q, end: e.target.value }))}
          />
        </label>
        <fieldset className="flex flex-wrap gap-3 sm:col-span-2">
          <legend className="text-sm font-medium">Send to</legend>
          {(channels.data ?? []).map((c) => (
            <label key={c.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={chosen.includes(c.id)}
                onChange={() =>
                  setChosen((s) => (s.includes(c.id) ? s.filter((x) => x !== c.id) : [...s, c.id]))
                }
              />
              {c.name}
            </label>
          ))}
        </fieldset>
        <div className="sm:col-span-2">
          <Button type="submit" disabled={add.isPending}>
            {C.alerts.addRule}
          </Button>
        </div>
      </form>
      <ErrorMessage error={add.error ?? remove.error} />
      <ul className="divide-border flex flex-col divide-y">
        {(rules.data ?? []).map((r) => (
          <li key={r.id} className="flex items-center justify-between gap-3 py-2 text-sm">
            <span>
              {r.name} —{" "}
              {r.kind === "drop" ? `drop of ${percent(r.margin)} or more` : `below ${percent(r.threshold)}`},
              over {r.window_days} days
              {r.open_alert_id ? <StatusBadge tone="danger">alert open</StatusBadge> : null}
            </span>
            <Button size="sm" variant="outline" onClick={() => remove.mutate(r.id)}>
              Remove
            </Button>
          </li>
        ))}
      </ul>
    </Section>
  )
}

function Incidents({ projectId }: { projectId: string }) {
  const alerts = useAlerts(projectId)
  const resolve = useResolveAlert(projectId)
  const check = useEvaluateAlerts(projectId)
  return (
    <Section
      title={C.alerts.incidents}
      action={
        <Button variant="outline" size="sm" disabled={check.isPending} onClick={() => check.mutate()}>
          {C.alerts.check}
        </Button>
      }
    >
      <ErrorMessage error={resolve.error ?? check.error} />
      {(alerts.data ?? []).length === 0 ? (
        <p className="text-text-secondary text-sm">{C.alerts.none}</p>
      ) : null}
      <ul className="divide-border flex flex-col divide-y">
        {(alerts.data ?? []).map((a) => (
          <li key={a.id} className="flex flex-col gap-1 py-3 text-sm">
            <div className="flex items-center justify-between gap-3">
              <span className="font-medium">{a.title}</span>
              {a.status === "open" ? (
                <span className="flex items-center gap-2">
                  <StatusBadge tone="danger">open</StatusBadge>
                  <Button size="sm" variant="outline" onClick={() => resolve.mutate(a.id)}>
                    {C.alerts.resolve}
                  </Button>
                </span>
              ) : (
                <StatusBadge tone="success">resolved</StatusBadge>
              )}
            </div>
            <p className="text-text-secondary">{String(a.detail.reason ?? "")}</p>
            <p className="text-text-muted text-xs">
              {new Date(a.created_at).toLocaleString()}
              {a.notified_at ? "" : " — waiting to be sent (quiet hours or no channel)"}
              {a.notify_results
                .filter((r) => !r.ok)
                .map((r) => ` — ${String(r.channel)}: ${String(r.error)}`)}
            </p>
          </li>
        ))}
      </ul>
    </Section>
  )
}

export function AlertsPanel({ projectId }: { projectId: string }) {
  return (
    <div className="flex flex-col gap-6">
      <Incidents projectId={projectId} />
      <Rules projectId={projectId} />
      <Channels projectId={projectId} />
    </div>
  )
}
