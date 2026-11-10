/** Sends one real test case to a saved app and explains what went out, what came back and how it was read. */
"use client"

import { CheckCircle2, XCircle } from "lucide-react"
import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

import { APPS_COPY } from "../copy"
import { explainReading, parseInputs, readCheck } from "../domain"
import { useTryApp } from "../hooks"

export function TrialPanel({
  projectId,
  appId,
  initialInputs,
  answerPath,
  idPrefix = "trial",
}: {
  projectId: string
  appId: string
  initialInputs: string
  answerPath: string
  idPrefix?: string
}) {
  const [text, setText] = useState(initialInputs)
  const trial = useTryApp(projectId)
  const shown = trial.data
  const reading = shown ? readCheck(shown) : null
  return (
    <div className="flex flex-col gap-3">
      <p className="text-text-muted text-xs">{APPS_COPY.testHint}</p>
      <Label htmlFor={`${idPrefix}-inputs`}>{APPS_COPY.testInputs}</Label>
      <Textarea
        id={`${idPrefix}-inputs`}
        className="font-mono text-xs"
        rows={3}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="flex flex-wrap items-center gap-3">
        <Button
          className="min-h-10"
          disabled={trial.isPending}
          onClick={() => trial.mutate({ appId, inputs: parseInputs(text) })}
        >
          {trial.isPending ? APPS_COPY.sending : APPS_COPY.testSend}
        </Button>
        {trial.error ? <ErrorMessage error={trial.error} /> : null}
      </div>
      {shown && reading ? (
        <div className="flex flex-col gap-2 text-xs" aria-live="polite">
          <p
            className={`flex items-center gap-1.5 text-sm font-medium ${reading.ok ? "text-success-strong" : "text-danger-strong"}`}
          >
            {reading.ok ? <CheckCircle2 className="size-4" /> : <XCircle className="size-4" />}
            {reading.headline}
          </p>
          {reading.fix ? <p className="text-text-secondary">{reading.fix}</p> : null}
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
              <ul className="text-text-secondary mt-1 list-disc pl-5">
                {explainReading(shown.reply, answerPath).map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
