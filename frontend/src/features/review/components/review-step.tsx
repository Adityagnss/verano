/**
 * Review answers: you mark answers good or bad, one card at a time, and Verano compares your marks with the
 * judge's. Also: giving answers out, who has labelled what, and disagreements an owner settles. Blind review
 * hides the judge's verdict while you label.
 */
"use client"

import { Undo2 } from "lucide-react"
import Link from "next/link"
import { useEffect, useRef, useState } from "react"

import { AnimatedNumber } from "@/components/common/animated-number"
import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { PageIntro } from "@/components/common/page-intro"
import { Section } from "@/components/common/section"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Kbd } from "@/components/ui/kbd"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import type { DisputeOut, ReviewItemOut } from "@/lib/api/types"
import { useAgreement } from "@/features/results/hooks"
import { useExperiments } from "@/features/run/hooks"
import { ALL_PROJECT_PAGES, projectHref } from "@/lib/nav"

import {
  useAssign,
  useDisputes,
  useLabelAnswer,
  useMyQueue,
  useResolve,
  useReviewMembers,
  useReviewProgress,
} from "../hooks"

export type Verdict = "good" | "bad" | "unsure"

/** Which card is shown: `offset` moves through the waiting answers without labelling them. */
export function pickCard<T>(items: T[], offset: number): { item: T | null; index: number } {
  if (items.length === 0) return { item: null, index: 0 }
  const index = ((offset % items.length) + items.length) % items.length
  return { item: items[index], index }
}

/** What a key does: give a verdict, or move; null for any other key. */
export function shortcutFor(key: string): Verdict | "next" | "previous" | null {
  switch (key.toLowerCase()) {
    case "g":
      return "good"
    case "b":
      return "bad"
    case "u":
      return "unsure"
    case "arrowright":
      return "next"
    case "arrowleft":
      return "previous"
    default:
      return null
  }
}

const VERDICT_LABEL: Record<Verdict, string> = {
  good: "Good answer",
  bad: "Bad answer",
  unsure: "Not sure",
}
const VERDICT_KEY: Record<Verdict, string> = { good: "G", bad: "B", unsure: "U" }

function AnswerBlock({
  inputs,
  output,
  expected,
}: {
  inputs: Record<string, unknown>
  output: string | null
  expected: string | null
}) {
  return (
    <div className="flex flex-col gap-3 text-sm">
      <div>
        <p className="text-text-muted text-xs font-medium">What was sent</p>
        <p className="break-words whitespace-pre-wrap">
          {Object.entries(inputs)
            .map(([k, v]) => `${k}: ${String(v)}`)
            .join("\n")}
        </p>
      </div>
      <div>
        <p className="text-text-muted text-xs font-medium">The answer</p>
        <p className="break-words whitespace-pre-wrap">{output ?? "No answer."}</p>
      </div>
      {expected ? (
        <div>
          <p className="text-text-muted text-xs font-medium">Expected answer</p>
          <p className="break-words whitespace-pre-wrap">{expected}</p>
        </div>
      ) : null}
    </div>
  )
}

function ReviewCard({
  projectId,
  item,
  position,
  total,
  onLabelled,
  onMove,
  canUndo,
  onUndo,
}: {
  projectId: string
  item: ReviewItemOut
  position: number
  total: number
  onLabelled: (item: ReviewItemOut) => void
  onMove: (step: 1 | -1) => void
  canUndo: boolean
  onUndo: () => void
}) {
  const label = useLabelAnswer(projectId)
  const [note, setNote] = useState(item.my_note ?? "")
  const latest = useRef({ item, note, pending: false })
  useEffect(() => {
    latest.current = { item, note, pending: label.isPending }
  })
  const set = (verdict: Verdict) => {
    const { item: it, note: n, pending } = latest.current
    if (pending) return
    label.mutate(
      {
        experimentId: it.experiment_id,
        runId: it.test_case_run_id,
        body: { verdict, note: n.trim() || null },
      },
      { onSuccess: () => onLabelled(it) },
    )
  }
  const setRef = useRef(set)
  useEffect(() => {
    setRef.current = set
  })
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const t = e.target as HTMLElement | null
      if (t && ["TEXTAREA", "INPUT", "SELECT"].includes(t.tagName)) return
      if (t?.isContentEditable) return
      const action = shortcutFor(e.key)
      if (!action) return
      e.preventDefault()
      if (action === "next") onMove(1)
      else if (action === "previous") onMove(-1)
      else setRef.current(action)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onMove])

  return (
    <article
      aria-label={`Answer ${position} of ${total}`}
      className="border-border bg-card flex flex-col gap-4 rounded-xl border p-4 sm:p-5"
    >
      <p className="text-text-muted text-xs">
        Answer {position} of {total} · {item.model} · {item.experiment_name}
        {item.batch_label ? ` · ${item.batch_label}` : ""}
        {item.hidden ? " · Blind review: the judge's verdict is hidden" : ""}
      </p>
      <AnswerBlock inputs={item.inputs} output={item.output} expected={item.expected_output} />
      {item.judge && !item.hidden ? (
        <p className="text-text-secondary text-sm">
          The judge says:{" "}
          <strong>
            {item.judge.passed === null ? "not scored" : item.judge.passed ? "good" : "not good"}
          </strong>
          {item.labels && item.labels.verdict !== "unlabelled"
            ? ` · people so far: ${item.labels.good} good, ${item.labels.bad} bad`
            : ""}
        </p>
      ) : null}
      <Textarea
        aria-label="A note (optional)"
        placeholder="A note (optional)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={2}
      />
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {(["good", "bad", "unsure"] as const).map((v) => (
          <Button
            key={v}
            size="lg"
            className="min-h-12 text-base"
            variant={item.my_label === v ? "default" : "outline"}
            disabled={label.isPending}
            onClick={() => set(v)}
          >
            {VERDICT_LABEL[v]}
            <Kbd className="ml-2 hidden sm:inline-flex">{VERDICT_KEY[v]}</Kbd>
          </Button>
        ))}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-text-muted hidden flex-wrap items-center gap-1 text-xs sm:flex">
          Keys: <Kbd>G</Kbd> good <Kbd>B</Kbd> bad <Kbd>U</Kbd> not sure <Kbd>←</Kbd>
          <Kbd>→</Kbd> move between answers
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            size="lg"
            variant="ghost"
            className="min-h-10"
            onClick={() => onMove(-1)}
            disabled={total < 2}
          >
            Previous
          </Button>
          <Button
            size="lg"
            variant="ghost"
            className="min-h-10"
            onClick={() => onMove(1)}
            disabled={total < 2}
          >
            Skip
          </Button>
          <Button size="lg" variant="outline" className="min-h-10" onClick={onUndo} disabled={!canUndo}>
            <Undo2 aria-hidden /> Undo last label
          </Button>
        </div>
      </div>
      <ErrorMessage error={label.error} />
    </article>
  )
}

export function AgreementMeter({
  raw,
  warn,
  tooFew,
  message,
  labelled,
  minLabels,
}: {
  raw: number | null
  warn: boolean
  tooFew: boolean
  message?: string
  labelled: number
  minLabels: number
}) {
  const pct = raw === null ? 0 : Math.round(raw * 100)
  return (
    <div
      className="border-border bg-card flex flex-col gap-2 rounded-xl border p-4"
      data-testid="agreement-meter"
    >
      <p className="text-text-muted text-xs font-medium">Agreement with the judge</p>
      {tooFew || raw === null ? (
        <p className="text-sm">
          Label {Math.max(0, minLabels - labelled)} more answers to see how often the judge agrees with you.
        </p>
      ) : (
        <>
          <AnimatedNumber value={pct} suffix="%" className="text-3xl font-semibold" />
          <div
            role="progressbar"
            aria-label="Agreement with the judge"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={pct}
            className="bg-muted h-2 overflow-hidden rounded-full"
          >
            <div
              className={`h-full rounded-full transition-[width] duration-500 motion-reduce:transition-none ${warn ? "bg-danger-strong" : "bg-success-strong"}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          {warn ? (
            <p className="text-danger-strong text-sm font-medium">
              Warning: the judge disagrees with you too often. Do not trust its scores yet.
            </p>
          ) : (
            <p className="text-success-strong text-sm">The judge agrees with you often enough.</p>
          )}
        </>
      )}
      {message ? <p className="text-text-secondary text-xs">{message}</p> : null}
    </div>
  )
}

function AssignForm({ projectId, experimentId }: { projectId: string; experimentId: string }) {
  const members = useReviewMembers(projectId)
  const assign = useAssign(projectId)
  const [who, setWho] = useState("")
  const [count, setCount] = useState("30")
  const [pick, setPick] = useState<"unlabelled" | "disputed">("unlabelled")
  const [blind, setBlind] = useState(false)
  const [batch, setBatch] = useState("")
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault()
        assign.mutate({
          experiment_id: experimentId,
          assignee_user_id: who || null,
          count: Math.max(1, Number(count) || 1),
          pick,
          blind,
          batch_label: batch.trim() || null,
        })
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rq-who">Give to</Label>
          <NativeSelect id="rq-who" value={who} onChange={(e) => setWho(e.target.value)}>
            <option value="">Me</option>
            {(members.data ?? []).map((m) => (
              <option key={m.user_id} value={m.user_id}>
                {m.name}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rq-count">How many answers</Label>
          <Input id="rq-count" inputMode="numeric" value={count} onChange={(e) => setCount(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rq-pick">Which answers</Label>
          <NativeSelect
            id="rq-pick"
            value={pick}
            onChange={(e) => setPick(e.target.value as "unlabelled" | "disputed")}
          >
            <option value="unlabelled">Nobody has labelled yet</option>
            <option value="disputed">Labels disagree</option>
          </NativeSelect>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rq-batch">Name (optional)</Label>
          <Input id="rq-batch" value={batch} onChange={(e) => setBatch(e.target.value)} />
        </div>
      </div>
      <label className="flex min-h-10 items-center gap-2 text-sm">
        <input type="checkbox" checked={blind} onChange={(e) => setBlind(e.target.checked)} />
        Blind: hide the judge&apos;s scores and verdicts while they label
      </label>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" size="lg" disabled={assign.isPending}>
          Give out answers
        </Button>
        {assign.data ? <span className="text-text-secondary text-sm">{assign.data.message}</span> : null}
      </div>
      <ErrorMessage error={assign.error} />
    </form>
  )
}

function Dispute({ projectId, item }: { projectId: string; item: DisputeOut }) {
  const resolve = useResolve(projectId)
  const [note, setNote] = useState(item.resolution?.note ?? "")
  const settle = (verdict: "good" | "bad") =>
    resolve.mutate({
      experimentId: item.experiment_id,
      runId: item.test_case_run_id,
      body: { verdict, note: note.trim() || null },
    })
  return (
    <li className="border-border bg-card flex flex-col gap-3 rounded-xl border p-4">
      <AnswerBlock inputs={item.inputs} output={item.output} expected={item.expected_output} />
      <ul className="text-text-secondary text-xs">
        {item.labels.map((l) => (
          <li key={l.user_id}>
            {l.name}: {l.verdict}
            {l.note ? ` (${l.note})` : ""}
          </li>
        ))}
      </ul>
      {item.resolution ? (
        <p className="text-sm font-medium">Final verdict: {item.resolution.verdict}</p>
      ) : null}
      <Textarea
        aria-label="Why"
        placeholder="Why (optional)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={2}
      />
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          className="min-h-10"
          variant="outline"
          disabled={resolve.isPending}
          onClick={() => settle("good")}
        >
          Settle as good
        </Button>
        <Button
          size="sm"
          className="min-h-10"
          variant="outline"
          disabled={resolve.isPending}
          onClick={() => settle("bad")}
        >
          Settle as bad
        </Button>
      </div>
      <ErrorMessage error={resolve.error} />
    </li>
  )
}

export function ReviewStep({ projectId }: { projectId: string }) {
  const experiments = useExperiments(projectId)
  const [chosen, setChosen] = useState("")
  const [blind, setBlind] = useState(false)
  const [offset, setOffset] = useState(0)
  const [last, setLast] = useState<ReviewItemOut | null>(null)
  const [revisit, setRevisit] = useState<ReviewItemOut | null>(null)
  const experimentId = chosen || experiments.data?.[0]?.id || null
  const queue = useMyQueue(projectId, "open", null, blind)
  const progress = useReviewProgress(projectId, experimentId)
  const disputes = useDisputes(projectId, experimentId)
  const agreement = useAgreement(projectId, experimentId)
  const resultsPage = ALL_PROJECT_PAGES.find((p) => p.key === "results")!

  const items = queue.data?.items ?? []
  const { item: current, index } = pickCard(items, offset)
  const shown = revisit ?? current
  const ag = agreement.data?.find((a) => a.warn) ?? agreement.data?.[0]
  const onMove = (step: 1 | -1) => {
    setRevisit(null)
    setOffset((o) => o + step)
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">
      <PageIntro
        storageKey="review"
        title="Review answers"
        what="You mark answers good or bad, and Verano compares your marks with the judge's."
        whenToUse="you are about to trust automatic scores"
        youGet="an agreement score, and a warning when the judge disagrees with you too often"
        learnMore="review"
        hasContent={items.length > 0}
      />

      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_16rem]">
        <section aria-label="Answers to check" className="flex min-w-0 flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-text-secondary text-sm">
              {queue.data
                ? `${queue.data.open} waiting for you, ${queue.data.done} done.`
                : "Answers given to you to label."}
            </p>
            <label className="flex min-h-10 items-center gap-2 text-sm">
              <input type="checkbox" checked={blind} onChange={(e) => setBlind(e.target.checked)} />
              Blind review: hide the judge&apos;s verdict
            </label>
          </div>
          {progress.data ? (
            <div className="flex flex-col gap-1">
              <div
                role="progressbar"
                aria-label="Answers labelled"
                aria-valuemin={0}
                aria-valuemax={Math.max(progress.data.assigned, 1)}
                aria-valuenow={progress.data.done}
                className="bg-muted h-2 overflow-hidden rounded-full"
              >
                <div
                  className="bg-lagoon-strong h-full rounded-full transition-[width] duration-500 motion-reduce:transition-none"
                  style={{
                    width: `${progress.data.assigned ? Math.round((progress.data.done / progress.data.assigned) * 100) : 0}%`,
                  }}
                />
              </div>
              <p className="text-text-muted text-xs">
                {progress.data.done} of {progress.data.assigned} labelled
              </p>
            </div>
          ) : null}
          <ErrorMessage error={queue.error} />
          {shown ? (
            <ReviewCard
              key={shown.assignment_id}
              projectId={projectId}
              item={shown}
              position={index + 1}
              total={Math.max(items.length, 1)}
              onLabelled={(it) => {
                setLast(it)
                setRevisit(null)
              }}
              onMove={onMove}
              canUndo={last !== null}
              onUndo={() => {
                setRevisit(last)
                setLast(null)
              }}
            />
          ) : queue.data ? (
            <EmptyState
              title="Nothing to check yet"
              description="Answers get here when you give them out below, or when a teammate gives you some. Run a test first, then look at its results."
              action={
                <Button size="lg" render={<Link href={projectHref(projectId, resultsPage)} />}>
                  {resultsPage.label}
                </Button>
              }
            />
          ) : null}
          <p className="text-text-muted text-xs">
            Why 30 answers? With fewer, a few lucky guesses can make a judge look better than it is. About 30
            marked answers give a steady agreement score.
          </p>
        </section>
        <aside aria-label="Agreement" className="flex flex-col gap-3">
          {ag ? (
            <AgreementMeter
              raw={ag.raw}
              warn={ag.warn}
              tooFew={ag.too_few}
              message={ag.message}
              labelled={ag.labelled_answers}
              minLabels={ag.min_labels}
            />
          ) : (
            <AgreementMeter raw={null} warn={false} tooFew labelled={0} minLabels={30} />
          )}
        </aside>
      </div>

      <Section
        title="Give out answers"
        description="Pick a test run, then who labels how many of its answers."
      >
        <div className="mb-3 flex flex-col gap-1.5 sm:max-w-sm">
          <Label htmlFor="rq-exp">Test run</Label>
          <NativeSelect id="rq-exp" value={experimentId ?? ""} onChange={(e) => setChosen(e.target.value)}>
            {(experiments.data ?? []).map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </NativeSelect>
        </div>
        {experimentId ? (
          <AssignForm projectId={projectId} experimentId={experimentId} />
        ) : (
          <p className="text-text-secondary text-sm">
            Run a test first, then come back to review its answers.
          </p>
        )}
      </Section>

      <Section
        title="Who has labelled what"
        description={
          progress.data
            ? `${progress.data.done} of ${progress.data.assigned} labelled; ${progress.data.disputed} disagreements waiting.`
            : "Who has labelled what."
        }
      >
        <ErrorMessage error={progress.error} />
        <ul className="text-sm">
          {(progress.data?.people ?? []).map((p) => (
            <li key={p.user_id}>
              {p.name}: {p.done} of {p.assigned} done
            </li>
          ))}
        </ul>
      </Section>

      <Section
        title="Disagreements"
        description="Answers where people disagree. A workspace owner settles each one; scores never change."
      >
        <ErrorMessage error={disputes.error} />
        {disputes.data && disputes.data.length === 0 ? (
          <p className="text-text-secondary text-sm">No disagreements.</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {(disputes.data ?? []).map((d) => (
              <Dispute key={d.test_case_run_id} projectId={projectId} item={d} />
            ))}
          </ul>
        )}
      </Section>
    </div>
  )
}
