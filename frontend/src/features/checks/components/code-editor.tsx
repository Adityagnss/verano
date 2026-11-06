/**
 * The code check editor: write `def check(case)`, try it on a sample answer in the sandbox (result, reason,
 * errors, the limits it runs under), then add it to the checks. Adding needs one successful try.
 */
"use client"

import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Textarea } from "@/components/ui/textarea"
import type { CodeTryOut, EvaluatorSetVersionOut } from "@/lib/api/types"

import { CHECKS_COPY } from "../copy"
import { CODE_TEMPLATE, codeCheckName, tryVerdict } from "../domain"
import { useCodeContract, useTryCode } from "../hooks"
import type { AddCheck } from "./check-library"

const COPY = CHECKS_COPY.code

function TryResult({ result }: { result: CodeTryOut }) {
  if (!result.ok || result.score === null)
    return (
      <div className="bg-danger-soft text-danger-strong rounded-lg p-3 text-sm" role="alert">
        <p className="font-semibold">{COPY.errorTitle}</p>
        <p>{result.timed_out ? COPY.timedOut : (result.error ?? result.reason)}</p>
      </div>
    )
  return (
    <div
      className={`${result.passed ? "bg-success-soft text-success-strong" : "bg-warning-soft text-warning-strong"} rounded-lg p-3 text-sm`}
      role="status"
    >
      <p className="font-semibold">{tryVerdict(result)}</p>
      {result.reason ? (
        <p>
          {COPY.reason}: {result.reason}
        </p>
      ) : null}
    </div>
  )
}

export function CodeEditor({
  projectId,
  set,
  frozen,
  busy,
  add,
}: {
  projectId: string
  set: EvaluatorSetVersionOut
  frozen: boolean
  busy: boolean
  add: AddCheck
}) {
  const contract = useCodeContract(projectId)
  const run = useTryCode(projectId)
  const [title, setTitle] = useState("")
  const [code, setCode] = useState(CODE_TEMPLATE)
  const [output, setOutput] = useState("")
  const [expected, setExpected] = useState("")
  const [input, setInput] = useState("")
  const [mark, setMark] = useState("50")
  const [triedCode, setTriedCode] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  if (contract.isPending) return <Skeleton className="h-40" aria-label={CHECKS_COPY.loading} />
  if (contract.error) return <ErrorMessage error={contract.error} />
  const { enabled, limits, max_code_chars: maxChars } = contract.data
  if (!enabled) return <p className="text-text-secondary text-sm">{COPY.off}</p>

  const worked = run.data?.ok === true && triedCode === code
  const markNumber = Number(mark)
  const markBad = !Number.isFinite(markNumber) || markNumber < 0 || markNumber > 100

  function tryIt() {
    setTriedCode(code)
    run.mutate({
      code,
      output,
      expected: expected.trim() ? expected : null,
      inputs: input.trim() ? { input } : {},
    })
  }

  function addIt() {
    const name = title.trim()
    if (!name) return setMessage(COPY.needTitle)
    if (!code.trim()) return setMessage(COPY.needCode)
    if (!worked) return setMessage(COPY.needTry)
    if (markBad) return setMessage("The pass mark must be between 0 and 100.")
    setMessage(null)
    void add(
      {
        evaluator_name: codeCheckName(
          name,
          set.evaluators.map((e) => e.evaluator_name),
        ),
        evaluator_version: "1",
        config: { kind: "code", code },
        threshold: markNumber / 100,
        weight: 1,
        required: false,
      },
      name,
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-text-secondary text-sm">{COPY.intro}</p>
      <div className="flex max-w-md flex-col gap-1.5">
        <Label htmlFor="code-name">{COPY.name}</Label>
        <Input
          id="code-name"
          value={title}
          maxLength={60}
          placeholder={COPY.namePlaceholder}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="code-body">{COPY.editor}</Label>
        <Textarea
          id="code-body"
          rows={10}
          spellCheck={false}
          autoCapitalize="off"
          maxLength={maxChars}
          className="font-mono text-xs"
          value={code}
          onChange={(e) => setCode(e.target.value)}
        />
        <p className="text-text-muted text-xs">{COPY.editorHint}</p>
        <p className="text-text-muted text-xs">{COPY.returns}</p>
        <p className="text-text-muted text-xs">{COPY.allowed}</p>
        <p className="text-text-muted text-xs">
          {COPY.limits(limits.wall_s, limits.memory_mb, limits.output_chars)}
        </p>
      </div>
      <fieldset className="bg-subtle ring-border flex flex-col gap-3 rounded-lg p-4 ring-1">
        <legend className="px-1 text-sm font-semibold">{COPY.tryHeading}</legend>
        <div className="grid gap-3 md:grid-cols-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="try-output">{COPY.sampleOutput}</Label>
            <Textarea id="try-output" rows={3} value={output} onChange={(e) => setOutput(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="try-expected">{COPY.sampleExpected}</Label>
            <Textarea
              id="try-expected"
              rows={3}
              value={expected}
              onChange={(e) => setExpected(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="try-input">{COPY.sampleInput}</Label>
            <Textarea id="try-input" rows={3} value={input} onChange={(e) => setInput(e.target.value)} />
          </div>
        </div>
        <Button
          className="self-start"
          variant="outline"
          disabled={run.isPending || !code.trim()}
          onClick={tryIt}
        >
          {run.isPending ? COPY.trying : COPY.tryButton}
        </Button>
        <ErrorMessage error={run.error} />
        {run.data && !run.isPending ? <TryResult result={run.data} /> : null}
      </fieldset>
      <div className="flex flex-wrap items-end gap-4">
        <div className="flex max-w-40 flex-col gap-1.5">
          <Label htmlFor="code-mark">{COPY.passMark} (%)</Label>
          <Input
            id="code-mark"
            type="number"
            min={0}
            max={100}
            value={mark}
            aria-invalid={markBad ? true : undefined}
            onChange={(e) => setMark(e.target.value)}
          />
        </div>
        <Button disabled={frozen || busy} onClick={addIt}>
          {busy ? CHECKS_COPY.adding : CHECKS_COPY.add}
        </Button>
      </div>
      {message ? (
        <p className="text-danger-strong text-sm" role="alert">
          {message}
        </p>
      ) : null}
    </div>
  )
}
