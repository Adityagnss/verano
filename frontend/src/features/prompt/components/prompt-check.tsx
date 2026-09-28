/**
 * The live review checklist beside the editor: the prompt's shape, its variables, what each
 * test case must provide, whether it fits each selected model's context window, and a
 * preview rendered with the first real test case when there is one.
 */
"use client"

import { CircleAlert, CircleCheck, CircleHelp } from "lucide-react"

import { ErrorMessage } from "@/components/common/error-message"
import type { InspectOut } from "@/lib/api/types"

import { PROMPT_COPY } from "../copy"

function Line({ tone, children }: { tone: "ok" | "bad" | "unknown"; children: React.ReactNode }) {
  const Icon = tone === "ok" ? CircleCheck : tone === "bad" ? CircleAlert : CircleHelp
  const color = tone === "ok" ? "text-success" : tone === "bad" ? "text-destructive" : "text-warning"
  return (
    <li className="flex items-start gap-2 text-sm">
      <Icon className={`mt-0.5 size-4 shrink-0 ${color}`} />
      <span>{children}</span>
    </li>
  )
}

export function PromptCheck({ result, error }: { result: InspectOut | undefined; error: unknown }) {
  if (error) return <ErrorMessage error={error} />
  if (!result) return <p className="text-muted-foreground text-sm">{PROMPT_COPY.reviewEmpty}</p>
  const { check, preview } = result
  return (
    <div className="flex flex-col gap-4">
      <ul className="flex flex-col gap-2">
        <Line tone="ok">{PROMPT_COPY.shape[check.shape]}</Line>
        <Line tone="ok">{PROMPT_COPY.variables(check.variables)}</Line>
        {check.required_inputs.length ? (
          <Line tone="ok">{PROMPT_COPY.inputsNeeded(check.required_inputs)}</Line>
        ) : null}
        {check.context.length === 0 ? <Line tone="unknown">{PROMPT_COPY.noModels}</Line> : null}
        {check.context.map((fit) => (
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
          <h4 className="text-muted-foreground text-xs font-medium uppercase">{PROMPT_COPY.preview}</h4>
          {preview.messages.map((message, index) => (
            <div key={index} className="bg-secondary rounded-lg p-3">
              <div className="text-muted-foreground mb-1 text-xs">{message.role}</div>
              <pre className="font-mono text-xs whitespace-pre-wrap">{message.content}</pre>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}
