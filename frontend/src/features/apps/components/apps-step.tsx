/**
 * Your apps: connect an app that Verano calls over HTTP, and send one test case to see exactly what went out and
 * what came back before any run. An app then appears next to the models on the Run step.
 */
"use client"

import { Trash2 } from "lucide-react"
import { useState } from "react"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { Section } from "@/components/common/section"
import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import type { AppTargetCreate, AppTargetOut } from "@/lib/api/types"

import { APPS_COPY } from "../copy"
import { parseInputs } from "../domain"
import { useAddApp, useApps, useRemoveApp, useTryApp } from "../hooks"

const DEFAULT_TEMPLATE = '{"question": {{ question | tojson }}}'
type AuthKind = "none" | "bearer" | "basic" | "headers"

function Field({
  id,
  label,
  hint,
  children,
}: {
  id: string
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint ? <p className="text-text-muted text-xs">{hint}</p> : null}
    </div>
  )
}

function AddForm({ projectId }: { projectId: string }) {
  const add = useAddApp(projectId)
  const [form, setForm] = useState({
    name: "",
    url: "",
    template: DEFAULT_TEMPLATE,
    answerPath: "$.answer",
    chunksPath: "",
    toolCallsPath: "",
    conversation: false,
    auth: "none" as AuthKind,
    bearer: "",
    user: "",
    password: "",
    headerName: "",
    headerValue: "",
  })
  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) =>
    setForm((f) => ({ ...f, [key]: value }))
  const submit = () => {
    const body: AppTargetCreate = {
      name: form.name.trim(),
      url: form.url.trim(),
      method: "POST",
      request_template: form.template,
      answer_path: form.answerPath.trim(),
      chunks_path: form.chunksPath.trim() || null,
      tool_calls_path: form.toolCallsPath.trim() || null,
      mode: form.conversation ? "conversation" : "single",
      auth_kind: form.auth,
      ...(form.auth === "bearer" ? { bearer_token: form.bearer } : {}),
      ...(form.auth === "basic" ? { basic_username: form.user, basic_password: form.password } : {}),
      headers: form.auth === "headers" && form.headerName ? { [form.headerName]: form.headerValue } : {},
    }
    add.mutate(body)
  }
  return (
    <Section title={APPS_COPY.addTitle} description={APPS_COPY.addDescription}>
      <form
        className="grid gap-4 md:grid-cols-2"
        onSubmit={(event) => {
          event.preventDefault()
          submit()
        }}
      >
        <Field id="app-name" label={APPS_COPY.fields.name}>
          <Input id="app-name" value={form.name} onChange={(e) => set("name", e.target.value)} required />
        </Field>
        <Field id="app-url" label={APPS_COPY.fields.url} hint={APPS_COPY.fields.urlHint}>
          <Input id="app-url" value={form.url} onChange={(e) => set("url", e.target.value)} required />
        </Field>
        <div className="md:col-span-2">
          <Field id="app-template" label={APPS_COPY.fields.template} hint={APPS_COPY.fields.templateHint}>
            <Textarea
              id="app-template"
              className="font-mono text-xs"
              rows={3}
              value={form.template}
              onChange={(e) => set("template", e.target.value)}
              required
            />
          </Field>
        </div>
        <Field id="app-answer" label={APPS_COPY.fields.answerPath} hint={APPS_COPY.fields.answerHint}>
          <Input
            id="app-answer"
            value={form.answerPath}
            onChange={(e) => set("answerPath", e.target.value)}
            required
          />
        </Field>
        <Field id="app-chunks" label={APPS_COPY.fields.chunksPath} hint={APPS_COPY.fields.chunksHint}>
          <Input
            id="app-chunks"
            value={form.chunksPath}
            onChange={(e) => set("chunksPath", e.target.value)}
          />
        </Field>
        <Field id="app-tools" label={APPS_COPY.fields.toolCallsPath} hint={APPS_COPY.fields.toolCallsHint}>
          <Input
            id="app-tools"
            value={form.toolCallsPath}
            onChange={(e) => set("toolCallsPath", e.target.value)}
          />
        </Field>
        <Field id="app-auth" label={APPS_COPY.fields.auth} hint={APPS_COPY.secretNote}>
          <select
            id="app-auth"
            className="border-input bg-background h-9 rounded-lg border px-3 text-sm"
            value={form.auth}
            onChange={(e) => set("auth", e.target.value as AuthKind)}
          >
            {(Object.keys(APPS_COPY.authKinds) as AuthKind[]).map((kind) => (
              <option key={kind} value={kind}>
                {APPS_COPY.authKinds[kind]}
              </option>
            ))}
          </select>
        </Field>
        {form.auth === "bearer" ? (
          <Field id="app-bearer" label={APPS_COPY.fields.bearer}>
            <Input
              id="app-bearer"
              type="password"
              value={form.bearer}
              onChange={(e) => set("bearer", e.target.value)}
            />
          </Field>
        ) : null}
        {form.auth === "basic" ? (
          <>
            <Field id="app-user" label={APPS_COPY.fields.basicUser}>
              <Input id="app-user" value={form.user} onChange={(e) => set("user", e.target.value)} />
            </Field>
            <Field id="app-password" label={APPS_COPY.fields.basicPassword}>
              <Input
                id="app-password"
                type="password"
                value={form.password}
                onChange={(e) => set("password", e.target.value)}
              />
            </Field>
          </>
        ) : null}
        {form.auth === "headers" ? (
          <>
            <Field id="app-header-name" label={APPS_COPY.fields.headerName}>
              <Input
                id="app-header-name"
                value={form.headerName}
                onChange={(e) => set("headerName", e.target.value)}
              />
            </Field>
            <Field id="app-header-value" label={APPS_COPY.fields.headerValue}>
              <Input
                id="app-header-value"
                type="password"
                value={form.headerValue}
                onChange={(e) => set("headerValue", e.target.value)}
              />
            </Field>
          </>
        ) : null}
        <label className="flex items-center gap-2 text-sm md:col-span-2">
          <input
            type="checkbox"
            checked={form.conversation}
            onChange={(e) => set("conversation", e.target.checked)}
          />
          {APPS_COPY.fields.conversation}
        </label>
        <div className="flex items-center gap-3 md:col-span-2">
          <Button type="submit" disabled={add.isPending}>
            {add.isPending ? APPS_COPY.adding : APPS_COPY.add}
          </Button>
          {add.error ? <ErrorMessage error={add.error} /> : null}
        </div>
      </form>
    </Section>
  )
}

function TryPanel({ projectId, app }: { projectId: string; app: AppTargetOut }) {
  const [text, setText] = useState("question=")
  const trial = useTryApp(projectId)
  const shown = trial.data
  return (
    <div className="border-border mt-3 flex flex-col gap-3 border-t pt-3">
      <p className="text-sm font-medium">{APPS_COPY.testTitle}</p>
      <p className="text-text-muted text-xs">{APPS_COPY.testHint}</p>
      <Label htmlFor={`inputs-${app.id}`} className="sr-only">
        {APPS_COPY.testInputs}
      </Label>
      <Textarea
        id={`inputs-${app.id}`}
        className="font-mono text-xs"
        rows={3}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="flex items-center gap-3">
        <Button
          size="sm"
          disabled={trial.isPending}
          onClick={() => trial.mutate({ appId: app.id, inputs: parseInputs(text) })}
        >
          {trial.isPending ? APPS_COPY.sending : APPS_COPY.testSend}
        </Button>
        {trial.error ? <ErrorMessage error={trial.error} /> : null}
      </div>
      {shown ? (
        <div className="flex flex-col gap-2 text-xs">
          <p className="text-text-muted font-medium">{APPS_COPY.sent}</p>
          <pre className="bg-subtle ring-border max-h-40 overflow-auto rounded-lg p-2 font-mono whitespace-pre-wrap ring-1">
            {shown.request_body || "(the request could not be filled in)"}
          </pre>
          <p className="text-text-muted font-medium">
            {APPS_COPY.received(shown.status_code, shown.latency_ms)}
          </p>
          <pre className="bg-subtle ring-border max-h-48 overflow-auto rounded-lg p-2 font-mono whitespace-pre-wrap ring-1">
            {shown.response_body ?? ""}
          </pre>
          {shown.truncated ? <p className="text-warning-strong">{APPS_COPY.truncated}</p> : null}
          {shown.error ? <p className="text-destructive">{shown.error}</p> : null}
          {shown.reply ? (
            <div className="flex flex-col gap-1">
              <p className="text-text-muted font-medium">{APPS_COPY.read}</p>
              <p>
                <span className="text-text-muted">{APPS_COPY.answer}: </span>
                {shown.reply.answer}
              </p>
              <p>
                <span className="text-text-muted">{APPS_COPY.chunks}: </span>
                {shown.reply.chunks.length ? shown.reply.chunks.join(" · ") : "–"}
              </p>
              <p>
                <span className="text-text-muted">{APPS_COPY.toolCalls}: </span>
                {shown.reply.tool_calls.length ? JSON.stringify(shown.reply.tool_calls) : "–"}
              </p>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

export function AppsStep({ projectId }: { projectId: string }) {
  const apps = useApps(projectId)
  const remove = useRemoveApp(projectId)
  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">{APPS_COPY.title}</h1>
        <p className="text-text-secondary max-w-2xl text-sm">{APPS_COPY.subtitle}</p>
      </header>
      {apps.error ? <ErrorMessage error={apps.error} /> : null}
      {(apps.data ?? []).length === 0 && !apps.isLoading ? (
        <EmptyState title={APPS_COPY.empty} description={APPS_COPY.addDescription} />
      ) : (
        <ul className="flex flex-col gap-3">
          {(apps.data ?? []).map((app) => (
            <li key={app.id} className="bg-card border-border rounded-xl border p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{app.name}</span>
                <StatusBadge tone="neutral">{APPS_COPY.mode(app.mode)}</StatusBadge>
                <span className="text-text-muted font-mono text-xs">
                  {app.method} {app.url}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="ml-auto"
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(app.id)}
                >
                  <Trash2 />
                  {APPS_COPY.remove}
                </Button>
              </div>
              <TryPanel projectId={projectId} app={app} />
            </li>
          ))}
        </ul>
      )}
      <AddForm projectId={projectId} />
    </div>
  )
}
