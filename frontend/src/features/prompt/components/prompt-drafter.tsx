/** "Write it for me": a first prompt drafted from the project's documents and an optional end goal. */
"use client"

import { useMutation } from "@tanstack/react-query"
import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useGeneratorSuggestion } from "@/features/tests/hooks"
import { api, call } from "@/lib/api/client"
import type { components } from "@/lib/api/schema"

type Draft = components["schemas"]["PromptDraft"]

export function PromptDrafter({
  projectId,
  onUse,
}: {
  projectId: string
  onUse: (draft: { system_template: string; user_template: string }) => void
}) {
  const [open, setOpen] = useState(false)
  const [goal, setGoal] = useState("")
  const suggestion = useGeneratorSuggestion(projectId)
  const model = suggestion.data?.suggested ?? null
  const write = useMutation({
    mutationFn: (): Promise<Draft> =>
      call(() =>
        api.POST("/api/v1/projects/{project_id}/generator/prompt-draft", {
          params: { path: { project_id: projectId } },
          body: { credential_id: model!.credential_id, model: model!.model, goal: goal.trim() || null },
        }),
      ),
  })
  const draft = write.data

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" className="min-h-10 self-start" />}>
        Write it for me
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Write the first prompt for me</DialogTitle>
          <DialogDescription>
            Verano reads the documents you added on the Add examples step and writes a prompt from them. An
            end goal is optional. You can edit the result before you save it.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="draft-goal">What should the prompt achieve? (optional)</Label>
          <Textarea
            id="draft-goal"
            rows={3}
            maxLength={1000}
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            placeholder="For example: answer customer questions about refunds using our policy."
          />
        </div>
        {model ? null : (
          <p className="text-text-secondary text-sm">Connect a model on the Connect models step first.</p>
        )}
        <ErrorMessage error={write.error} />
        {draft ? (
          <div className="flex flex-col gap-3">
            <ul className="list-disc pl-5 text-sm">
              {(draft.reasons ?? []).map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
            <pre className="bg-card ring-border max-h-56 overflow-auto rounded-lg p-2 font-mono text-xs whitespace-pre-wrap ring-1">
              {draft.system_template}
              {"\n\n"}
              {draft.user_template}
            </pre>
          </div>
        ) : null}
        <DialogFooter>
          <Button
            variant={draft ? "outline" : "default"}
            className="min-h-10"
            disabled={!model || write.isPending}
            onClick={() => write.mutate()}
          >
            {write.isPending ? "Writing…" : draft ? "Write another" : "Write the prompt"}
          </Button>
          {draft ? (
            <Button
              className="min-h-10"
              onClick={() => {
                onUse(draft)
                setOpen(false)
              }}
            >
              Use this prompt
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
