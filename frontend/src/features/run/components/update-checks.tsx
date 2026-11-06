/**
 * "Update checks to the current defaults" (ADR 0039): shows what would be added, changed and (only if you choose)
 * removed, then applies it as a new version of the checks. Nothing changes until you confirm.
 */
"use client"

import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"

import { useApplyDefaults, useDefaultsPreview } from "../extras-hooks"

const COPY = {
  open: "Check for newer default checks",
  close: "Close",
  title: "Update checks to the current defaults",
  apply: "Update checks",
  working: "Updating…",
  leaveOut: "Leave this out",
  removeIt: "Remove this check",
  done: "Updated. The next run uses the new checks. Earlier runs keep the checks they were scored with.",
  actions: {
    add: "New",
    change: "Changes",
    same: "Same",
    keep: "Yours",
    remove: "Not in the defaults",
  },
} as const

export function UpdateChecks({
  projectId,
  versionId,
  onApplied,
}: {
  projectId: string
  versionId: string
  onApplied: (newVersionId: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [skip, setSkip] = useState<string[]>([])
  const [remove, setRemove] = useState<string[]>([])
  const [done, setDone] = useState<string | null>(null)
  const preview = useDefaultsPreview(projectId, versionId, open)
  const apply = useApplyDefaults(projectId, versionId)
  const toggle = (list: string[], set: (next: string[]) => void, name: string) =>
    set(list.includes(name) ? list.filter((n) => n !== name) : [...list, name])

  if (!open)
    return (
      <div className="flex flex-col gap-1.5">
        <div>
          <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>
            {COPY.open}
          </Button>
        </div>
        {done ? <p className="text-text-muted text-xs">{done}</p> : null}
      </div>
    )

  const lines = (preview.data?.lines ?? []).filter((line) => line.action !== "same")
  return (
    <div className="bg-subtle ring-border flex flex-col gap-3 rounded-lg p-3 text-sm ring-1">
      <p className="font-medium">{COPY.title}</p>
      <ErrorMessage error={preview.error ?? apply.error} />
      {preview.data ? <p>{preview.data.summary}</p> : null}
      <ul className="flex flex-col gap-2">
        {lines.map((line) => (
          <li key={line.name} className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <span className="font-medium">{line.name}</span>
              <span className="text-text-muted text-xs">{COPY.actions[line.action]}</span>
            </div>
            <p className="text-text-muted text-xs">{line.note}</p>
            {line.differences.map((d) => (
              <p key={d.field} className="text-xs">
                <span className="font-medium">{d.field}:</span> {d.before ?? "(none)"} → {d.after ?? "(none)"}
              </p>
            ))}
            {line.action === "change" || line.action === "add" ? (
              <label className="flex items-center gap-2 text-xs">
                <Checkbox
                  checked={skip.includes(line.name)}
                  onCheckedChange={() => toggle(skip, setSkip, line.name)}
                />
                {COPY.leaveOut}
              </label>
            ) : null}
            {line.action === "remove" ? (
              <label className="flex items-center gap-2 text-xs">
                <Checkbox
                  checked={remove.includes(line.name)}
                  onCheckedChange={() => toggle(remove, setRemove, line.name)}
                />
                {COPY.removeIt}
              </label>
            ) : null}
          </li>
        ))}
      </ul>
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          disabled={!preview.data || preview.data.up_to_date || apply.isPending}
          onClick={() =>
            apply.mutate(
              { skip, remove },
              {
                onSuccess: (result) => {
                  setDone(result.created ? COPY.done : result.note)
                  onApplied(result.version.id)
                  setOpen(false)
                },
              },
            )
          }
        >
          {apply.isPending ? COPY.working : COPY.apply}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => setOpen(false)}>
          {COPY.close}
        </Button>
      </div>
    </div>
  )
}
