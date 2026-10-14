/**
 * The pop-up shown when Improve finishes with a proven better prompt: the full prompt, what changed and
 * how much better it scored, and the choice to save it as the next version or reject it. A version saved here
 * is the latest one, so the next round (Run, then Improve again) starts from it. A rejected result is
 * remembered in this browser only, so the pop-up does not return; the candidate stays on the page.
 */
"use client"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import type { CandidateOut } from "@/lib/api/types"

import { IMPROVE_COPY } from "../copy"
import { percent } from "./candidate-card"

export function ResultDialog({
  open,
  candidate,
  before,
  after,
  busy,
  onSave,
  onSaveAndTest,
  onReject,
}: {
  open: boolean
  candidate: CandidateOut
  before: number | null
  after: number | null
  busy: boolean
  onSave: () => void
  onSaveAndTest: () => void
  onReject: () => void
}) {
  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onReject())}>
      <DialogContent className="flex max-h-[90vh] flex-col sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{IMPROVE_COPY.result.title}</DialogTitle>
          <DialogDescription>
            {IMPROVE_COPY.result.summary(candidate.strategy, percent(before), percent(after))}
          </DialogDescription>
        </DialogHeader>
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
          {candidate.change_reasons.length ? (
            <div>
              <p className="text-muted-foreground text-xs font-medium">{IMPROVE_COPY.result.changes}</p>
              <ul className="list-disc pl-5 text-sm">
                {candidate.change_reasons.map((reason, index) => (
                  <li key={index}>{String(reason)}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {[
            [IMPROVE_COPY.systemPrompt, candidate.system_template],
            [IMPROVE_COPY.userPrompt, candidate.user_template],
          ].map(([label, text]) =>
            text ? (
              <div key={label}>
                <p className="text-muted-foreground text-xs font-medium">{label}</p>
                <pre className="bg-card ring-border max-h-72 overflow-auto rounded-lg p-3 font-mono text-xs whitespace-pre-wrap ring-1">
                  {text}
                </pre>
              </div>
            ) : null,
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onReject} disabled={busy}>
            {IMPROVE_COPY.result.reject}
          </Button>
          <Button variant="outline" onClick={onSave} disabled={busy}>
            {IMPROVE_COPY.result.save}
          </Button>
          <Button onClick={onSaveAndTest} disabled={busy}>
            {IMPROVE_COPY.result.saveAndTest}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
