/**
 * Labels on the prompt: which saved version each label (production, staging, your own) points at, assigning and
 * removing them, rolling one back in a single click, the "move on accept" choice (off by default) and the history of
 * moves with who and when.
 */
"use client"

import { useState } from "react"
import { toast } from "sonner"

import { ErrorMessage } from "@/components/common/error-message"
import { Section } from "@/components/common/section"
import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useCurrentPrompt, usePromptVersions } from "@/features/prompt/hooks"

import { LABELS_COPY as COPY } from "../copy"
import {
  useAcceptMovesLabel,
  useLabelHistory,
  useLabels,
  useRemoveLabel,
  useRollBackLabel,
  useSetLabel,
} from "../hooks"

const SELECT =
  "border-input bg-background h-9 rounded-md border px-2 text-sm focus-visible:ring-3 focus-visible:ring-ring/50 outline-none"

export function LabelsPanel({ projectId }: { projectId: string }) {
  const prompt = useCurrentPrompt(projectId)
  const promptId = prompt.data?.id ?? null
  if (!promptId) return null
  return <Loaded projectId={projectId} promptId={promptId} />
}

function Loaded({ projectId, promptId }: { projectId: string; promptId: string }) {
  const labels = useLabels(projectId, promptId)
  const history = useLabelHistory(projectId, promptId)
  const versions = usePromptVersions(projectId, promptId)
  const set = useSetLabel(projectId, promptId)
  const rollBack = useRollBackLabel(projectId, promptId)
  const remove = useRemoveLabel(projectId, promptId)
  const acceptMoves = useAcceptMovesLabel(projectId, promptId)
  const [choice, setChoice] = useState("production")
  const [custom, setCustom] = useState("")
  const [versionId, setVersionId] = useState("")

  const name = (custom.trim() || choice).toLowerCase()
  const target = versionId || versions.data?.[0]?.id || ""
  const current = labels.data?.accept_moves_label ?? null
  const moveOn = current !== null
  const moveLabel = current ?? "production"

  async function assign() {
    const saved = await set.mutateAsync({ name, versionId: target })
    setCustom("")
    toast.success(COPY.setDone(saved.name, saved.version))
  }

  return (
    <Section title={COPY.title} description={COPY.description}>
      <ErrorMessage
        error={
          labels.error ?? history.error ?? set.error ?? rollBack.error ?? remove.error ?? acceptMoves.error
        }
      />
      {labels.data && labels.data.labels.length === 0 ? (
        <p className="text-text-secondary text-sm">{COPY.empty}</p>
      ) : null}
      <ul className="flex flex-col gap-2">
        {(labels.data?.labels ?? []).map((label) => (
          <li
            key={label.name}
            className="border-border flex flex-wrap items-center gap-3 rounded-lg border px-3 py-2"
          >
            <StatusBadge tone="brand">{label.name}</StatusBadge>
            <span className="text-sm font-medium">
              {COPY.version} {label.version}
            </span>
            <span className="text-text-secondary text-xs">
              {COPY.moved(new Date(label.moved_at).toLocaleString())}
            </span>
            <span className="ml-auto flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={!label.can_roll_back || rollBack.isPending}
                title={label.can_roll_back ? undefined : COPY.cannotRollBack}
                onClick={async () => {
                  const back = await rollBack.mutateAsync(label.name)
                  toast.success(COPY.rolledBack(back.name, back.version))
                }}
              >
                {COPY.rollBack}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={remove.isPending}
                onClick={async () => {
                  await remove.mutateAsync(label.name)
                  toast.success(COPY.removed(label.name))
                }}
              >
                {COPY.remove}
              </Button>
            </span>
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          {COPY.name}
          <select className={SELECT} value={choice} onChange={(e) => setChoice(e.target.value)}>
            {COPY.suggested.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <Input
          className="w-48"
          aria-label={COPY.customPlaceholder}
          placeholder={COPY.customPlaceholder}
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
        />
        <label className="flex flex-col gap-1 text-sm">
          {COPY.version}
          <select className={SELECT} value={target} onChange={(e) => setVersionId(e.target.value)}>
            {(versions.data ?? []).map((v) => (
              <option key={v.id} value={v.id}>
                {v.version}
              </option>
            ))}
          </select>
        </label>
        <Button disabled={!target || set.isPending} onClick={assign}>
          {COPY.set}
        </Button>
      </div>

      <div className="border-border flex flex-col gap-2 border-t pt-4">
        <h4 className="text-sm font-semibold">{COPY.acceptHeading}</h4>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="radio"
            name="accept-moves"
            checked={!moveOn}
            onChange={async () => {
              await acceptMoves.mutateAsync(null)
              toast.success(COPY.acceptSaved)
            }}
          />
          {COPY.acceptOff}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="radio"
            name="accept-moves"
            checked={moveOn}
            onChange={async () => {
              await acceptMoves.mutateAsync(moveLabel)
              toast.success(COPY.acceptSaved)
            }}
          />
          {COPY.acceptOn(moveLabel)}
        </label>
        <p className="text-text-secondary text-xs">{COPY.acceptHelp}</p>
      </div>

      <div className="border-border flex flex-col gap-2 border-t pt-4">
        <h4 className="text-sm font-semibold">{COPY.historyHeading}</h4>
        {history.data && history.data.length === 0 ? (
          <p className="text-text-secondary text-sm">{COPY.historyEmpty}</p>
        ) : null}
        <ul className="flex flex-col gap-1 text-sm">
          {(history.data ?? []).map((move) => (
            <li key={move.id} className="flex flex-wrap gap-2">
              <span className="font-medium">{move.label}</span>
              <span>{COPY.historyLine(move.from_version, move.to_version)}</span>
              <span className="text-text-secondary">
                {COPY.reasons[move.reason] ?? move.reason} {COPY.by(move.moved_by_name)} ·{" "}
                {new Date(move.created_at).toLocaleString()}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Section>
  )
}
