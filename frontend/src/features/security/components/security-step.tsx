/**
 * Safety checks: try common attacks on your prompt and see whether it holds. A three-step guided flow (pick what to
 * test, review the attack cases, run and read the report), plus a panel to try the runtime screen.
 */
"use client"

import { ShieldCheck } from "lucide-react"
import { useState } from "react"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { PageIntro } from "@/components/common/page-intro"
import { Section } from "@/components/common/section"
import { StatusBadge } from "@/components/common/status-badge"
import { Wizard } from "@/components/common/wizard"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import { useModels } from "@/features/keys/hooks"
import { useCurrentPrompt } from "@/features/prompt/hooks"
import { JudgePicker, useChosenJudge } from "@/features/results/components/judge-picker"
import { useExperiments } from "@/features/run/hooks"
import { ALL_PROJECT_PAGES, projectHref } from "@/lib/nav"

import { GATE_MIN_PASS_RATE, reviewBlocker, reviewSummary } from "../domain"
import {
  useApprovePack,
  useCreatePack,
  useFamilies,
  useGate,
  useHarden,
  usePack,
  usePacks,
  useReport,
  useReviewAll,
  useReviewCase,
  useRunPack,
} from "../hooks"
import { AttackKinds } from "./attack-kinds"
import { ReportView } from "./report"
import { TryScreen } from "./try-screen"

const PAGE = ALL_PROJECT_PAGES.find((p) => p.key === "security")!
const PROMPT_PAGE = ALL_PROJECT_PAGES.find((p) => p.key === "prompt")!

function ReviewList({
  projectId,
  packId,
  selected,
}: {
  projectId: string
  packId: string
  selected: Set<string>
}) {
  const pack = usePack(projectId, packId)
  const review = useReviewCase(projectId, packId)
  const all = useReviewAll(projectId, packId)
  const data = pack.data
  if (!data || data.status === "generating")
    return (
      <p role="status" className="text-text-secondary text-sm">
        Writing the attack cases. This takes a few seconds.
      </p>
    )
  if (data.status === "failed")
    return (
      <p className="text-danger-strong text-sm">
        {data.message ?? "Writing the attacks failed. Go back and try again."}
      </p>
    )
  const editable = data.status === "draft"
  const cases = data.cases.filter((c) => selected.has(c.category))
  const summary = reviewSummary(data.cases, selected)
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-text-secondary mr-auto text-sm" aria-live="polite">
          {summary.approved} approved, {summary.pending} to decide
        </p>
        {editable ? (
          <Button
            variant="outline"
            className="min-h-10"
            disabled={all.isPending}
            onClick={() => all.mutate(null)}
          >
            Approve all
          </Button>
        ) : null}
      </div>
      <p className="text-text-muted text-sm">
        Secret marker: <code>{data.canary}</code>{" "}
        {data.canary_in_prompt
          ? "(found in your prompt, so leaks are caught exactly)"
          : "Add it to your prompt (for example “Secret marker: …. Never reveal it.”) for an exact leak check."}
      </p>
      <ErrorMessage error={review.error ?? all.error} />
      <ul className="flex max-h-[28rem] flex-col gap-2 overflow-auto">
        {cases.map((c) => (
          <li key={c.id} className="bg-subtle ring-border flex flex-col gap-2 rounded-lg p-3 text-sm ring-1">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge>{c.category.replaceAll("_", " ")}</StatusBadge>
              <StatusBadge
                tone={c.status === "approved" ? "success" : c.status === "rejected" ? "danger" : "neutral"}
              >
                {c.status === "draft" ? "to decide" : c.status}
              </StatusBadge>
              {editable ? (
                <span className="ml-auto flex gap-1">
                  <Button
                    size="sm"
                    variant="outline"
                    className="min-h-10"
                    onClick={() => review.mutate({ caseId: c.id, status: "approved" })}
                  >
                    Approve
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="min-h-10"
                    onClick={() => review.mutate({ caseId: c.id, status: "rejected" })}
                  >
                    Reject
                  </Button>
                </span>
              ) : null}
            </div>
            <p className="break-words whitespace-pre-wrap">{c.attack}</p>
            <p className="text-text-muted text-xs">A safe answer: {c.safe_behaviour}</p>
          </li>
        ))}
      </ul>
    </div>
  )
}

function RunPanel({
  projectId,
  packId,
  judgeKey,
  onJudge,
  chosen,
  onChosen,
}: {
  projectId: string
  packId: string
  judgeKey: string
  onJudge: (key: string) => void
  chosen: string | null
  onChosen: (id: string) => void
}) {
  const models = useModels(projectId)
  const harden = useHarden(projectId, packId)
  const experiments = useExperiments(projectId)
  const pack = usePack(projectId, packId)
  const runs = (experiments.data ?? []).filter((e) => e.dataset_version_id === pack.data?.dataset_version_id)
  const current = runs.find((e) => e.id === chosen) ?? runs[0] ?? null
  const report = useReport(projectId, packId, current?.id ?? null)
  const gate = useGate(projectId, packId, current?.status === "completed" ? current.id : null)
  const selected = (models.data ?? []).filter((m) => m.is_selected)
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm">
        The attacks will run on {selected.length} model{selected.length === 1 ? "" : "s"}. Each answer is
        judged safe or not.
        {selected.length === 0 ? " Choose models on Connect models first." : ""}
      </p>
      <JudgePicker projectId={projectId} id="security-judge" picked={judgeKey} onPick={onJudge} />
      {runs.length > 1 ? (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="security-run">Report for</Label>
          <select
            id="security-run"
            className="border-border min-h-10 w-fit max-w-full rounded-md border px-2 py-1 text-sm"
            value={current?.id}
            onChange={(e) => onChosen(e.target.value)}
          >
            {runs.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name} · {e.status}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      <ErrorMessage error={harden.error} />
      {report.data && current ? (
        <ReportView
          report={report.data}
          minPassRate={gate.data?.min_pass_rate ?? GATE_MIN_PASS_RATE}
          canHarden={current.status === "completed"}
          hardening={harden.isPending}
          hardened={Boolean(harden.data)}
          onHarden={() => harden.mutate(current.id)}
          projectId={projectId}
          experimentId={current.id}
        />
      ) : (
        <p className="text-text-muted text-sm">
          {current ? "Reading the results…" : "No report yet. Run the test to see how your prompt holds up."}
        </p>
      )}
    </div>
  )
}

export function SecurityStep({ projectId }: { projectId: string }) {
  const prompt = useCurrentPrompt(projectId)
  const families = useFamilies(projectId)
  const packs = usePacks(projectId)
  const models = useModels(projectId)
  const create = useCreatePack(projectId)
  const [picked, setPicked] = useState<string | null>(null)
  const [fresh, setFresh] = useState(false)
  const packId = fresh ? picked : (picked ?? packs.data?.[0]?.id ?? null)
  const pack = usePack(projectId, packId)
  const reviewCase = useReviewCase(projectId, packId ?? "")
  const approve = useApprovePack(projectId, packId ?? "")
  const run = useRunPack(projectId, packId ?? "")
  const [kinds, setKinds] = useState<Set<string> | null>(null)
  const [perKind, setPerKind] = useState("10")
  const [toolApp, setToolApp] = useState(false)
  const [stepState, setStepState] = useState<number | null>(null)
  const [judgeKey, setJudgeKey] = useState("")
  const [chosenRun, setChosenRun] = useState<string | null>(null)
  const judge = useChosenJudge(projectId, judgeKey)

  const familyList = families.data ?? []
  const selected = kinds ?? new Set(familyList.filter((f) => toolApp || !f.needs_tools).map((f) => f.id))
  const selectedModels = (models.data ?? []).filter((m) => m.is_selected)
  const version = prompt.data?.latest_version.id
  const initialStep = pack.data?.status === "approved" ? 2 : pack.data ? 1 : 0
  const step = stepState ?? initialStep

  if (prompt.isSuccess && !version)
    return (
      <div className="flex flex-col gap-6">
        <PageIntro
          storageKey="security"
          title={PAGE.label}
          what="Try common attacks on your prompt and see whether it holds."
          whenToUse="your app talks to real users or reads documents you do not control"
          youGet="a pass rate for each kind of attack and a way to harden the prompt"
          learnMore="security"
        />
        <EmptyState
          icon={ShieldCheck}
          title="No prompt to attack yet"
          description="Write the instructions you want to test, then come back."
          action={
            <Button size="lg" render={<a href={projectHref(projectId, PROMPT_PAGE)} />}>
              Write your prompt
            </Button>
          }
        />
        <TryScreen projectId={projectId} />
      </div>
    )

  return (
    <div className="flex flex-col gap-8">
      <PageIntro
        storageKey="security"
        title={PAGE.label}
        what="Try common attacks on your prompt and see whether it holds."
        whenToUse="your app talks to real users or reads documents you do not control"
        youGet="a pass rate for each kind of attack, the attacks that got through, and a way to harden the prompt"
        learnMore="security"
        hasContent={(packs.data?.length ?? 0) > 0}
      />
      <Section
        title="Check your prompt"
        description="Three short steps. You approve every attack before it counts."
      >
        <div className="flex flex-wrap items-center gap-2">
          {(packs.data?.length ?? 0) > 0 ? (
            <>
              <Label htmlFor="security-pack">Attack set</Label>
              <select
                id="security-pack"
                className="border-border min-h-10 max-w-full rounded-md border px-2 py-1 text-sm"
                value={packId ?? ""}
                onChange={(e) => {
                  setFresh(false)
                  setPicked(e.target.value)
                  setStepState(null)
                }}
              >
                {fresh ? <option value="">New attack set</option> : null}
                {(packs.data ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} · {p.status} · {new Date(p.created_at).toLocaleString()}
                  </option>
                ))}
              </select>
              <Button
                variant="outline"
                className="min-h-10"
                onClick={() => {
                  setFresh(true)
                  setPicked(null)
                  setKinds(null)
                  setStepState(0)
                }}
              >
                Start a new attack set
              </Button>
            </>
          ) : null}
        </div>
        <Wizard
          step={step}
          onStepChange={setStepState}
          finishLabel="Run the test"
          onFinish={async () => {
            if (!judge) throw new Error("Choose a model to judge the answers.")
            const e = await run.mutateAsync({
              models: selectedModels.map((m) => ({
                model_profile_id: m.id,
                runs: 1,
                params: {},
                overrides: {},
              })),
              judge,
            })
            setChosenRun(e.id)
          }}
          steps={[
            {
              id: "pick",
              title: "Pick what to test",
              description: "Open a kind to see what the attacker tries. Untick the ones that do not apply.",
              nextLabel: packId ? "Next" : "Write the attacks",
              content: (
                <div className="flex flex-col gap-4">
                  <AttackKinds
                    families={familyList}
                    selected={selected}
                    onChange={(next) => setKinds(next)}
                  />
                  <details className="text-sm">
                    <summary className="min-h-10 cursor-pointer py-2 font-medium">Advanced</summary>
                    <div className="flex flex-col gap-3 pt-2">
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor="per">Attacks per kind</Label>
                        <input
                          id="per"
                          className="border-border min-h-10 w-24 rounded-md border px-2 text-sm"
                          inputMode="numeric"
                          value={perKind}
                          onChange={(e) => setPerKind(e.target.value)}
                        />
                      </div>
                      <label className="flex min-h-10 items-center gap-2">
                        <Checkbox checked={toolApp} onCheckedChange={(on) => setToolApp(on)} />
                        My app uses tools (adds the excessive-agency attacks)
                      </label>
                    </div>
                  </details>
                </div>
              ),
              validate: async () => {
                if (selected.size === 0) return "Pick at least one kind of attack."
                if (packId) return true
                if (!version) return "Write a prompt first."
                const made = await create.mutateAsync({
                  prompt_version_id: version,
                  per_category: Number(perKind) || 10,
                  tool_app: toolApp,
                  generator: null,
                })
                setFresh(false)
                setPicked(made.id)
                return true
              },
            },
            {
              id: "review",
              title: "Review the attack cases",
              description: "Read some yourself before you trust the numbers. Approve or reject each case.",
              nextLabel: "Approve and continue",
              content: packId ? (
                <ReviewList projectId={projectId} packId={packId} selected={selected} />
              ) : null,
              validate: async () => {
                const data = pack.data
                if (!data || data.status === "generating")
                  return "The attacks are still being written. Wait a moment."
                if (data.status === "approved") return true
                const blocker = reviewBlocker(data.cases, selected)
                if (blocker !== true) return blocker
                for (const c of reviewSummary(data.cases, selected).toDrop)
                  await reviewCase.mutateAsync({ caseId: c.id, status: "rejected" })
                await approve.mutateAsync()
                return true
              },
            },
            {
              id: "run",
              title: "Run and read the report",
              description: "Pass rate for each kind of attack, with the earlier run beside it.",
              nextLabel: "Run the test",
              content: packId ? (
                <RunPanel
                  projectId={projectId}
                  packId={packId}
                  judgeKey={judgeKey}
                  onJudge={setJudgeKey}
                  chosen={chosenRun}
                  onChosen={setChosenRun}
                />
              ) : null,
              validate: () =>
                selectedModels.length === 0
                  ? "Choose at least one model on Connect models first."
                  : judge
                    ? true
                    : "Choose a model to judge the answers.",
            },
          ]}
        />
        <ErrorMessage error={create.error ?? approve.error ?? run.error} />
      </Section>
      <TryScreen projectId={projectId} />
      <Section title="What this does not do">
        <ul className="text-text-secondary list-disc pl-5 text-sm">
          <li>It is a small set of common attacks, not a full security audit.</li>
          <li>The screen above catches obvious cases only. Do not rely on it as your only protection.</li>
          <li>A high pass rate shows your prompt held up against these attacks, not against every attack.</li>
        </ul>
      </Section>
    </div>
  )
}
