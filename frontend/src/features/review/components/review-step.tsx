/**
 * Review queue: answers given to you to label, who else has been given how many, and disagreements between
 * labels that an owner settles. Blind mode hides the judge's scores and verdicts while you label.
 */
"use client"

import { useState } from "react"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { Section } from "@/components/common/section"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import type { DisputeOut, ReviewItemOut } from "@/lib/api/types"
import { useExperiments } from "@/features/run/hooks"

import {
  useAssign,
  useDisputes,
  useLabelAnswer,
  useMyQueue,
  useResolve,
  useReviewMembers,
  useReviewProgress,
} from "../hooks"

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
    <div className="flex flex-col gap-2 text-sm">
      <div>
        <p className="text-text-muted text-xs font-medium">What was sent</p>
        <p className="whitespace-pre-wrap">
          {Object.entries(inputs)
            .map(([k, v]) => `${k}: ${String(v)}`)
            .join("\n")}
        </p>
      </div>
      <div>
        <p className="text-text-muted text-xs font-medium">The answer</p>
        <p className="whitespace-pre-wrap">{output ?? "No answer."}</p>
      </div>
      {expected ? (
        <div>
          <p className="text-text-muted text-xs font-medium">Expected answer</p>
          <p className="whitespace-pre-wrap">{expected}</p>
        </div>
      ) : null}
    </div>
  )
}

function QueueItem({ projectId, item }: { projectId: string; item: ReviewItemOut }) {
  const label = useLabelAnswer(projectId)
  const [note, setNote] = useState(item.my_note ?? "")
  const set = (verdict: "good" | "bad" | "unsure") =>
    label.mutate({
      experimentId: item.experiment_id,
      runId: item.test_case_run_id,
      body: { verdict, note: note.trim() || null },
    })
  return (
    <li className="border-border bg-card flex flex-col gap-3 rounded-xl border p-4">
      <p className="text-text-muted text-xs">
        {item.experiment_name}
        {item.batch_label ? ` · ${item.batch_label}` : ""}
        {item.hidden ? " · blind: the judge's scores are hidden" : ""}
      </p>
      <AnswerBlock inputs={item.inputs} output={item.output} expected={item.expected_output} />
      {item.judge ? (
        <p className="text-text-secondary text-xs">
          The judge says:{" "}
          {item.judge.passed === null ? "not scored" : item.judge.passed ? "good" : "not good"}
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
      <div className="flex flex-wrap items-center gap-2">
        {(["good", "bad", "unsure"] as const).map((v) => (
          <Button
            key={v}
            size="sm"
            variant={item.my_label === v ? "default" : "outline"}
            disabled={label.isPending}
            onClick={() => set(v)}
          >
            {v === "good" ? "Good answer" : v === "bad" ? "Bad answer" : "Not sure"}
          </Button>
        ))}
        {item.done ? <span className="text-text-muted text-xs">You labelled this.</span> : null}
      </div>
      <ErrorMessage error={label.error} />
    </li>
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
      <div className="grid gap-3 sm:grid-cols-4">
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
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={blind} onChange={(e) => setBlind(e.target.checked)} />
        Blind: hide the judge&apos;s scores and verdicts while they label
      </label>
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={assign.isPending}>
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
      <div className="flex gap-2">
        <Button size="sm" variant="outline" disabled={resolve.isPending} onClick={() => settle("good")}>
          Settle as good
        </Button>
        <Button size="sm" variant="outline" disabled={resolve.isPending} onClick={() => settle("bad")}>
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
  const [status, setStatus] = useState<"open" | "done">("open")
  const [blind, setBlind] = useState(false)
  const experimentId = chosen || experiments.data?.[0]?.id || null
  const queue = useMyQueue(projectId, status, null, blind)
  const progress = useReviewProgress(projectId, experimentId)
  const disputes = useDisputes(projectId, experimentId)

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-xl font-semibold">Review queue</h1>
        <p className="text-text-secondary text-sm">
          Label answers as good or bad so Verano can tell how far to trust its judges.
        </p>
      </header>

      <Section
        title="Your queue"
        description={
          queue.data
            ? `${queue.data.open} waiting for you, ${queue.data.done} done.`
            : "Answers given to you to label."
        }
        action={
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={blind} onChange={(e) => setBlind(e.target.checked)} />
              Blind
            </label>
            <NativeSelect
              aria-label="Show"
              value={status}
              onChange={(e) => setStatus(e.target.value as "open" | "done")}
            >
              <option value="open">Waiting</option>
              <option value="done">Done</option>
            </NativeSelect>
          </div>
        }
      >
        <ErrorMessage error={queue.error} />
        {queue.data && queue.data.items.length === 0 ? (
          <EmptyState
            title={status === "open" ? "Nothing waiting" : "Nothing labelled yet"}
            description="Give yourself or a teammate some answers below, and they will show up here."
          />
        ) : (
          <ul className="flex flex-col gap-3">
            {(queue.data?.items ?? []).map((item) => (
              <QueueItem key={item.assignment_id} projectId={projectId} item={item} />
            ))}
          </ul>
        )}
      </Section>

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
        title="Progress"
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
