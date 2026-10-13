/**
 * The live review checklist beside the editor: the prompt's shape, its variables, what each
 * test case must provide, whether it fits each selected model's context window, and a
 * preview rendered with the first real test case when there is one.
 */
"use client"

import { CircleAlert, CircleCheck, CircleHelp } from "lucide-react"
import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import type { InspectOut } from "@/lib/api/types"

import { PROMPT_COPY } from "../copy"

function Line({ tone, children }: { tone: "ok" | "bad" | "unknown"; children: React.ReactNode }) {
  const Icon = tone === "ok" ? CircleCheck : tone === "bad" ? CircleAlert : CircleHelp
  const color = tone === "ok" ? "text-success" : tone === "bad" ? "text-danger" : "text-warning"
  return (
    <li className="flex items-start gap-2 text-sm">
      <Icon className={`mt-0.5 size-4 shrink-0 ${color}`} />
      <span>{children}</span>
    </li>
  )
}

function PreviewMessage({ role, content }: { role: string; content: string }) {
  const [open, setOpen] = useState(false)
  const long = content.length > 600
  return (
    <div className="bg-subtle ring-border rounded-lg p-3 ring-1">
      <div className="text-text-secondary mb-1 flex items-center justify-between gap-2 text-xs font-medium">
        <span className="capitalize">{role}</span>
        <span className="font-normal">{PROMPT_COPY.characters(content.length)}</span>
      </div>
      <pre
        className={`font-mono text-xs break-words whitespace-pre-wrap ${open ? "max-h-96 overflow-y-auto" : "max-h-32 overflow-hidden"}`}
      >
        {content}
      </pre>
      {long ? (
        <button
          type="button"
          className="text-lagoon-strong mt-1 text-xs font-medium hover:underline"
          onClick={() => setOpen(!open)}
        >
          {open ? PROMPT_COPY.showLess : PROMPT_COPY.showAll}
        </button>
      ) : null}
    </div>
  )
}

export function PromptCheck({ result, error }: { result: InspectOut | undefined; error: unknown }) {
  if (error) return <ErrorMessage error={error} />
  if (!result) return <p className="text-muted-foreground text-sm">{PROMPT_COPY.reviewEmpty}</p>
  const { check, preview } = result
  const allFit =
    check.context.length > 1 &&
    check.context.every(
      (fit) => fit.fits === true && fit.estimated_tokens === check.context[0].estimated_tokens,
    )
  return (
    <div className="flex flex-col gap-4">
      <ul className="flex flex-col gap-2">
        <Line tone="ok">{PROMPT_COPY.shape[check.shape]}</Line>
        <Line tone="ok">{PROMPT_COPY.variables(check.variables)}</Line>
        {check.required_inputs.length ? (
          <Line tone="ok">{PROMPT_COPY.inputsNeeded(check.required_inputs)}</Line>
        ) : null}
        {check.warnings.map((warning) => (
          <Line key={warning} tone="unknown">
            {warning}
          </Line>
        ))}
        {check.context.length === 0 ? <Line tone="unknown">{PROMPT_COPY.noModels}</Line> : null}
        {allFit ? (
          <Line tone="ok">
            {PROMPT_COPY.fitsAll(check.context.length, check.context[0].estimated_tokens)}
          </Line>
        ) : null}
        {(allFit ? [] : check.context).map((fit) => (
          <Line key={fit.model_profile_id} tone={fit.fits === null ? "unknown" : fit.fits ? "ok" : "bad"}>
            {fit.fits === null
              ? PROMPT_COPY.unknownWindow(fit.display_name)
              : fit.fits
                ? PROMPT_COPY.fits(fit.display_name, fit.estimated_tokens)
                : PROMPT_COPY.tooLong(fit.display_name, fit.estimated_tokens)}
          </Line>
        ))}
      </ul>
      {preview ? (
        <div className="flex flex-col gap-2">
          <h4 className="text-text-secondary text-sm font-medium">{PROMPT_COPY.preview}</h4>
          {preview.messages.map((message, index) => (
            <PreviewMessage key={index} role={message.role} content={message.content} />
          ))}
        </div>
      ) : null}
    </div>
  )
}
