/**
 * "What the judge saw": every request the judge got about one answer, exactly as it was sent
 * (including the instructions Verano adds so the reply can be read), and what it replied.
 * Loaded only when asked for.
 */
"use client"

import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"
import type { JudgeCallOut } from "@/lib/api/types"

import { RESULTS_COPY } from "../copy"
import { useJudgeCalls } from "../hooks"

export function JudgeCallList({ calls }: { calls: JudgeCallOut[] }) {
  if (calls.length === 0) return <p className="text-text-muted text-xs">{RESULTS_COPY.judgeNoCalls}</p>
  return (
    <ol className="flex flex-col gap-3">
      {calls.map((call, index) => (
        <li key={call.id} className="flex flex-col gap-1.5">
          <p className="text-text-muted text-xs font-medium">
            {RESULTS_COPY.judgeCall(index + 1, calls.length, call.evaluator)} · {call.model}
            {call.preview ? ` ${RESULTS_COPY.judgePreview}` : ""}
          </p>
          <pre className="bg-subtle ring-border max-h-64 overflow-auto rounded-lg p-2 font-mono text-xs whitespace-pre-wrap ring-1">
            {call.request_messages
              .map((m) => String((m as { content?: unknown }).content ?? ""))
              .join("\n\n")}
          </pre>
          <p className="text-text-muted text-xs">
            {call.error_message ? RESULTS_COPY.judgeFailed : RESULTS_COPY.judgeReply}:
          </p>
          <pre className="bg-subtle ring-border max-h-40 overflow-auto rounded-lg p-2 font-mono text-xs whitespace-pre-wrap ring-1">
            {call.error_message ?? call.output_text ?? ""}
          </pre>
        </li>
      ))}
    </ol>
  )
}

export function JudgeCalls({
  projectId,
  experimentId,
  answerId,
}: {
  projectId: string
  experimentId: string
  answerId: string
}) {
  const [open, setOpen] = useState(false)
  const calls = useJudgeCalls(projectId, experimentId, answerId, open)
  return (
    <div className="mt-2 flex flex-col gap-2">
      <Button
        variant="ghost"
        size="sm"
        className="self-start"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        {open ? RESULTS_COPY.hideJudge : RESULTS_COPY.seeJudge}
      </Button>
      {open ? (
        <>
          <ErrorMessage error={calls.error} />
          {calls.data ? <JudgeCallList calls={calls.data} /> : null}
        </>
      ) : null}
    </div>
  )
}
