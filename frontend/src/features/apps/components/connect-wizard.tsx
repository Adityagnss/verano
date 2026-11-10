/**
 * The three-step flow for connecting an app: where it is, what it expects, try one case.
 * Verano can only call an app it has saved, so the first check (or Next) saves a draft that later steps
 * update; cancelling removes a draft that was never finished.
 */
"use client"

import { CheckCircle2, ChevronDown, ChevronRight, Loader2, XCircle } from "lucide-react"
import { useRef, useState } from "react"

import { Wizard } from "@/components/common/wizard"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"

import { APPS_COPY } from "../copy"
import {
  addressProblem,
  type AppDraft,
  applyTemplate,
  type AuthKind,
  type CheckReading,
  emptyDraft,
  parseInputs,
  previewRequest,
  readCheck,
  sampleInputs,
  TEMPLATES,
  type TemplateId,
  toCreateBody,
} from "../domain"
import { useAddApp, useChangeApp, useRemoveApp, useTryApp } from "../hooks"
import { TrialPanel } from "./trial-panel"

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

export function ConnectWizard({
  projectId,
  onDone,
  onCancel,
  onChecked,
}: {
  projectId: string
  onDone: () => void
  onCancel: () => void
  onChecked?: (appId: string, reading: CheckReading, ms: number | null) => void
}) {
  const [draft, setDraft] = useState<AppDraft>(emptyDraft)
  const [advanced, setAdvanced] = useState(false)
  const [check, setCheck] = useState<CheckReading | null>(null)
  const [checking, setChecking] = useState(false)
  const appId = useRef<string | null>(null)
  const [savedId, setSavedId] = useState<string | null>(null)
  const add = useAddApp(projectId)
  const change = useChangeApp(projectId)
  const remove = useRemoveApp(projectId)
  const tryApp = useTryApp(projectId)
  const set = <K extends keyof AppDraft>(key: K, value: AppDraft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }))

  /** Saves the draft as it is now: creates the app the first time, updates it after that. */
  async function save(): Promise<string> {
    const body = toCreateBody(draft)
    if (appId.current) {
      await change.mutateAsync({ appId: appId.current, body })
      return appId.current
    }
    const created = await add.mutateAsync(body)
    appId.current = created.id
    setSavedId(created.id)
    return created.id
  }

  async function runCheck() {
    const problem = addressProblem(draft.url)
    if (problem) {
      setCheck({ ok: false, headline: problem, fix: null })
      return
    }
    setChecking(true)
    setCheck(null)
    try {
      const id = await save()
      const result = await tryApp.mutateAsync({
        appId: id,
        inputs: parseInputs(sampleInputs(draft.requestTemplate, "Hello")),
      })
      const reading = readCheck(result)
      setCheck(reading)
      onChecked?.(id, reading, result.latency_ms)
    } catch (caught) {
      setCheck({
        ok: false,
        headline: "Verano could not save or check the app.",
        fix: caught instanceof Error ? caught.message : "Try again in a moment.",
      })
    } finally {
      setChecking(false)
    }
  }

  async function cancel() {
    if (appId.current) {
      try {
        await remove.mutateAsync(appId.current)
      } catch {
        /* the draft stays in the list; it can be removed from there */
      }
    }
    onCancel()
  }

  const preview = previewRequest(draft.requestTemplate, parseInputs(sampleInputs(draft.requestTemplate)))
  const customOpen = draft.template === "custom"

  const requestFields = (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="md:col-span-2">
        <Field id="app-template-body" label={APPS_COPY.fields.template} hint={APPS_COPY.fields.templateHint}>
          <Textarea
            id="app-template-body"
            className="font-mono text-xs"
            rows={3}
            value={draft.requestTemplate}
            onChange={(e) => set("requestTemplate", e.target.value)}
          />
        </Field>
      </div>
      <Field id="app-answer" label={APPS_COPY.fields.answerPath} hint={APPS_COPY.fields.answerHint}>
        <Input id="app-answer" value={draft.answerPath} onChange={(e) => set("answerPath", e.target.value)} />
      </Field>
      <Field id="app-chunks" label={APPS_COPY.fields.chunksPath} hint={APPS_COPY.fields.chunksHint}>
        <Input id="app-chunks" value={draft.chunksPath} onChange={(e) => set("chunksPath", e.target.value)} />
      </Field>
      <Field id="app-tools" label={APPS_COPY.fields.toolCallsPath} hint={APPS_COPY.fields.toolCallsHint}>
        <Input
          id="app-tools"
          value={draft.toolCallsPath}
          onChange={(e) => set("toolCallsPath", e.target.value)}
        />
      </Field>
    </div>
  )

  const step1 = (
    <div className="flex flex-col gap-4">
      <Field id="app-url" label={APPS_COPY.fields.url} hint={APPS_COPY.fields.urlHint}>
        <Input
          id="app-url"
          inputMode="url"
          placeholder="https://my-app.example.com/ask"
          value={draft.url}
          onChange={(e) => {
            set("url", e.target.value)
            setCheck(null)
          }}
        />
      </Field>
      <Field id="app-name" label={`${APPS_COPY.fields.name} (optional)`}>
        <Input id="app-name" value={draft.name} onChange={(e) => set("name", e.target.value)} />
      </Field>
      <div className="flex flex-col gap-2">
        <Button variant="outline" className="min-h-10 self-start" disabled={checking} onClick={runCheck}>
          {checking ? <Loader2 className="animate-spin" /> : null}
          {checking ? APPS_COPY.checking : APPS_COPY.check}
        </Button>
        <div aria-live="polite">
          {check ? (
            <div
              className={cn(
                "flex items-start gap-2 rounded-lg p-3 text-sm ring-1",
                check.ok
                  ? "bg-success-soft text-success-strong ring-success/20"
                  : "bg-danger-soft text-danger-strong ring-danger/20",
              )}
            >
              {check.ok ? (
                <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
              ) : (
                <XCircle className="mt-0.5 size-4 shrink-0" />
              )}
              <div className="min-w-0 break-words">
                <p className="font-medium">{check.headline}</p>
                {check.fix ? <p className="mt-1">{check.fix}</p> : null}
              </div>
            </div>
          ) : null}
        </div>
        <p className="text-text-muted text-xs">{APPS_COPY.checkNote}</p>
      </div>
    </div>
  )

  const step2 = (
    <div className="flex flex-col gap-5">
      <div role="radiogroup" aria-label={APPS_COPY.fields.templatePick} className="grid gap-3 sm:grid-cols-2">
        {TEMPLATES.map((t) => {
          const selected = draft.template === t.id
          return (
            <button
              key={t.id}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => setDraft((d) => applyTemplate(d, t.id as TemplateId))}
              className={cn(
                "bg-card focus-visible:ring-ring min-h-10 rounded-xl border p-3 text-left outline-none focus-visible:ring-2",
                selected ? "border-lagoon-strong bg-lagoon-soft" : "border-border",
              )}
            >
              <span className="block text-sm font-medium">{t.title}</span>
              <span className="text-text-secondary block text-xs">{t.description}</span>
            </button>
          )
        })}
      </div>
      {customOpen ? requestFields : null}
      <div className="flex flex-col gap-1.5">
        <p className="text-sm font-medium">{APPS_COPY.previewTitle}</p>
        <pre
          aria-label={APPS_COPY.previewTitle}
          className="bg-subtle ring-border max-h-48 overflow-auto rounded-lg p-2 font-mono text-xs whitespace-pre-wrap ring-1"
        >
          {`POST ${draft.url.trim() || "your address"}\n${preview}`}
        </pre>
        <p className="text-text-muted text-xs">
          {APPS_COPY.previewNote(draft.answerPath || "the answer path")}
        </p>
      </div>
      <div className="border-border rounded-xl border">
        <button
          type="button"
          aria-expanded={advanced}
          onClick={() => setAdvanced((v) => !v)}
          className="focus-visible:ring-ring flex min-h-10 w-full items-center gap-2 rounded-xl px-3 text-sm font-medium outline-none focus-visible:ring-2"
        >
          {advanced ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
          {APPS_COPY.advanced}
        </button>
        {advanced ? (
          <div className="flex flex-col gap-4 border-t p-3">
            {!customOpen ? requestFields : null}
            <div className="grid gap-4 md:grid-cols-2">
              <Field id="app-auth" label={APPS_COPY.fields.auth} hint={APPS_COPY.secretNote}>
                <select
                  id="app-auth"
                  className="border-input bg-background h-10 rounded-lg border px-3 text-sm"
                  value={draft.auth}
                  onChange={(e) => set("auth", e.target.value as AuthKind)}
                >
                  {(Object.keys(APPS_COPY.authKinds) as AuthKind[]).map((kind) => (
                    <option key={kind} value={kind}>
                      {APPS_COPY.authKinds[kind]}
                    </option>
                  ))}
                </select>
              </Field>
              {draft.auth === "bearer" ? (
                <Field id="app-bearer" label={APPS_COPY.fields.bearer}>
                  <Input
                    id="app-bearer"
                    type="password"
                    value={draft.bearer}
                    onChange={(e) => set("bearer", e.target.value)}
                  />
                </Field>
              ) : null}
              {draft.auth === "basic" ? (
                <>
                  <Field id="app-user" label={APPS_COPY.fields.basicUser}>
                    <Input id="app-user" value={draft.user} onChange={(e) => set("user", e.target.value)} />
                  </Field>
                  <Field id="app-password" label={APPS_COPY.fields.basicPassword}>
                    <Input
                      id="app-password"
                      type="password"
                      value={draft.password}
                      onChange={(e) => set("password", e.target.value)}
                    />
                  </Field>
                </>
              ) : null}
              {draft.auth === "headers" ? (
                <>
                  <Field id="app-header-name" label={APPS_COPY.fields.headerName}>
                    <Input
                      id="app-header-name"
                      value={draft.headerName}
                      onChange={(e) => set("headerName", e.target.value)}
                    />
                  </Field>
                  <Field id="app-header-value" label={APPS_COPY.fields.headerValue}>
                    <Input
                      id="app-header-value"
                      type="password"
                      value={draft.headerValue}
                      onChange={(e) => set("headerValue", e.target.value)}
                    />
                  </Field>
                </>
              ) : null}
              <Field id="app-timeout" label={APPS_COPY.fields.timeout} hint={APPS_COPY.fields.timeoutHint}>
                <Input
                  id="app-timeout"
                  inputMode="numeric"
                  value={draft.timeout}
                  onChange={(e) => set("timeout", e.target.value.replace(/[^0-9]/g, ""))}
                />
              </Field>
            </div>
            <label className="flex min-h-10 items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={draft.conversation}
                onChange={(e) => set("conversation", e.target.checked)}
              />
              {APPS_COPY.fields.conversation}
            </label>
          </div>
        ) : null}
      </div>
    </div>
  )

  const step3 = savedId ? (
    <TrialPanel
      projectId={projectId}
      appId={savedId}
      initialInputs={sampleInputs(draft.requestTemplate)}
      answerPath={draft.answerPath}
      idPrefix="wizard-trial"
    />
  ) : null

  return (
    <Wizard
      finishLabel={APPS_COPY.save}
      onCancel={() => void cancel()}
      onFinish={async () => {
        await save()
        onDone()
      }}
      steps={[
        {
          id: "where",
          title: "Where is your app?",
          description: "Paste the address Verano should send questions to.",
          content: step1,
          validate: () => addressProblem(draft.url) ?? true,
        },
        {
          id: "expects",
          title: "What does it expect?",
          description: "Pick the shape that matches your app. You can change the details later.",
          content: step2,
          validate: async () => {
            if (!draft.requestTemplate.trim()) return "Write what to send to your app."
            if (!draft.answerPath.trim()) return "Say where the answer is in the reply, for example $.answer."
            await save()
            return true
          },
        },
        {
          id: "try",
          title: "Try one test case",
          description: "Send one real question and see how Verano reads the reply.",
          content: step3,
        },
      ]}
    />
  )
}
