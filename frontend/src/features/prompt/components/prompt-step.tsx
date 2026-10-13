/**
 * Step 2, Prompt: two optional text areas (at least one filled), default parameters and a
 * live check on the right. Saving always creates a new version; the previous ones stay.
 */
"use client"

import { useRouter } from "next/navigation"
import { useMemo, useState } from "react"
import { toast } from "sonner"

import { ErrorMessage } from "@/components/common/error-message"
import { PageActions } from "@/components/common/page-actions"
import { Section } from "@/components/common/section"
import { DiffView } from "@/components/common/diff-view"
import { StatusBadge } from "@/components/common/status-badge"
import { StepHeader } from "@/components/common/step-header"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useModels } from "@/features/keys/hooks"
import { useFirstCase } from "@/features/tests/hooks"
import type { PromptVersionOut } from "@/lib/api/types"
import { diffCounts, lineDiff, promptText } from "@/lib/diff"
import { useDebounced } from "@/lib/use-debounced"

import { PROMPT_COPY } from "../copy"
import {
  type Draft,
  defaultParams,
  useCurrentPrompt,
  useInspect,
  usePromptVersions,
  useSavePrompt,
} from "../hooks"
import { PromptCheck } from "./prompt-check"

const EMPTY: Draft = {
  name: "",
  system_template: "",
  user_template: "",
  temperature: "",
  max_tokens: "",
  change_reason: "",
}

function fromVersion(name: string, version: PromptVersionOut): Draft {
  const params = version.default_params as Record<string, unknown>
  return {
    name,
    system_template: version.system_template ?? "",
    user_template: version.user_template ?? "",
    temperature: params.temperature === undefined ? "" : String(params.temperature),
    max_tokens: params.max_tokens === undefined ? "" : String(params.max_tokens),
    change_reason: "",
  }
}

function sameAsSaved(draft: Draft, saved: Draft | null): boolean {
  if (!saved) return false
  return (
    draft.system_template === saved.system_template &&
    draft.user_template === saved.user_template &&
    JSON.stringify(defaultParams(draft)) === JSON.stringify(defaultParams(saved))
  )
}

export function PromptStep({ projectId }: { projectId: string }) {
  const router = useRouter()
  const current = useCurrentPrompt(projectId)
  const models = useModels(projectId)
  const firstCase = useFirstCase(projectId)
  const saved = useMemo(
    () => (current.data ? fromVersion(current.data.name, current.data.latest_version) : null),
    [current.data],
  )
  const [edits, setDraft] = useState<Draft | null>(null)
  const [loaded, setLoaded] = useState<number | null>(null)
  const draft = edits ?? saved ?? EMPTY
  const versions = usePromptVersions(projectId, current.data?.id ?? null)
  const latestNumber = current.data?.latest_version.version ?? 0

  const selectedIds = useMemo(
    () => (models.data ?? []).filter((m) => m.is_selected).map((m) => m.id),
    [models.data],
  )
  const settled = useDebounced(draft, 400)
  const inspect = useInspect(projectId, settled, selectedIds, firstCase.data?.inputs ?? null)
  const save = useSavePrompt(projectId, current.data?.id ?? null)

  const set = (field: keyof Draft) => (event: { target: { value: string } }) =>
    setDraft({ ...draft, [field]: event.target.value })
  const empty = !draft.system_template.trim() && !draft.user_template.trim()
  const unchanged = sameAsSaved(draft, saved) && (loaded === null || loaded === latestNumber)

  async function submit() {
    const version = await save.mutateAsync(draft)
    setLoaded(null)
    setDraft(null)
    toast.success(PROMPT_COPY.version(version.version))
    router.push(`/projects/${projectId}/data`)
  }

  return (
    <div className="mx-auto flex w-full max-w-[96rem] flex-col gap-6">
      <StepHeader
        projectId={projectId}
        step="prompt"
        title={PROMPT_COPY.title}
        description={PROMPT_COPY.subtitle}
        howItWorks={PROMPT_COPY.howItWorks}
      />
      <ErrorMessage error={current.error} />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
        <Section
          number={1}
          title={PROMPT_COPY.editorHeading}
          description={PROMPT_COPY.editorHint}
          badge={
            current.data ? (
              <StatusBadge tone="neutral">
                {PROMPT_COPY.versionBadge(current.data.latest_version.version)}
              </StatusBadge>
            ) : null
          }
        >
          {current.data ? null : (
            <div className="flex max-w-sm flex-col gap-1.5">
              <Label htmlFor="name">{PROMPT_COPY.name}</Label>
              <Input
                id="name"
                value={draft.name}
                onChange={set("name")}
                placeholder={PROMPT_COPY.namePlaceholder}
              />
            </div>
          )}
          {(["system_template", "user_template"] as const).map((field) => (
            <div key={field} className="flex flex-col gap-1.5">
              <Label htmlFor={field}>
                {field === "system_template" ? PROMPT_COPY.system : PROMPT_COPY.user}
              </Label>
              <p className="text-muted-foreground text-xs">
                {field === "system_template" ? PROMPT_COPY.systemHint : PROMPT_COPY.userHint}
              </p>
              <Textarea
                id={field}
                value={draft[field]}
                onChange={set(field)}
                rows={field === "system_template" ? 14 : 6}
                className="font-mono"
                spellCheck={false}
              />
            </div>
          ))}
          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-medium">{PROMPT_COPY.parameters}</h3>
            <div className="grid max-w-md grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="temperature">{PROMPT_COPY.temperature}</Label>
                <Input
                  id="temperature"
                  type="number"
                  step="0.1"
                  min={0}
                  max={2}
                  value={draft.temperature}
                  onChange={set("temperature")}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="max_tokens">{PROMPT_COPY.maxTokens}</Label>
                <Input
                  id="max_tokens"
                  type="number"
                  min={1}
                  value={draft.max_tokens}
                  onChange={set("max_tokens")}
                />
              </div>
            </div>
          </div>
          {current.data ? (
            <div className="flex max-w-xl flex-col gap-1.5">
              <Label htmlFor="change_reason">{PROMPT_COPY.changeReason}</Label>
              <Input id="change_reason" value={draft.change_reason} onChange={set("change_reason")} />
            </div>
          ) : null}
          {current.data && (versions.data?.length ?? 0) > 1 ? (
            <div className="border-border flex flex-col gap-2 border-t pt-4">
              <h3 className="text-sm font-medium">{PROMPT_COPY.versionsHeading}</h3>
              <p className="text-muted-foreground text-xs">{PROMPT_COPY.versionsHint}</p>
              <ul className="border-border divide-border divide-y rounded-lg border">
                {(versions.data ?? []).map((v) => {
                  const showing = (loaded ?? latestNumber) === v.version
                  const all = versions.data ?? []
                  const parent =
                    all.find((x) => x.id === v.parent_version_id) ??
                    all.find((x) => x.version === v.version - 1)
                  const changes = parent ? lineDiff(promptText(parent), promptText(v)) : null
                  const counts = changes ? diffCounts(changes) : null
                  return (
                    <li key={v.id} className="flex flex-col gap-2 px-3 py-2 text-sm">
                      <div className="flex items-center gap-3">
                        <span className="w-10 font-semibold tabular-nums">V{v.version}</span>
                        <span className="text-text-secondary min-w-0 flex-1 truncate">
                          {v.change_reason || PROMPT_COPY.noReason}
                        </span>
                        <span className="text-text-muted hidden text-xs sm:inline">
                          {new Date(v.created_at).toLocaleString()}
                        </span>
                        {v.version === latestNumber ? (
                          <StatusBadge tone="neutral">{PROMPT_COPY.latest}</StatusBadge>
                        ) : null}
                        {showing ? (
                          <span className="text-text-muted w-28 text-right text-xs">
                            {PROMPT_COPY.loaded}
                          </span>
                        ) : (
                          <Button
                            variant="outline"
                            size="sm"
                            className="w-28"
                            onClick={() => {
                              setDraft(fromVersion(current.data?.name ?? "", v))
                              setLoaded(v.version)
                            }}
                          >
                            {PROMPT_COPY.load}
                          </Button>
                        )}
                      </div>
                      {changes && counts ? (
                        <details className="text-xs">
                          <summary className="text-accent cursor-pointer">
                            {PROMPT_COPY.whatChanged(parent?.version ?? 0, counts.added, counts.removed)}
                          </summary>
                          <div className="mt-2">
                            <DiffView lines={changes} />
                          </div>
                        </details>
                      ) : null}
                    </li>
                  )
                })}
              </ul>
            </div>
          ) : null}
        </Section>
        <Section
          number={2}
          title={PROMPT_COPY.review}
          description={PROMPT_COPY.reviewHint}
          className="h-fit lg:sticky lg:top-20 lg:max-h-[calc(100vh-6.5rem)] lg:overflow-y-auto"
        >
          <PromptCheck result={empty ? undefined : inspect.data} error={empty ? null : inspect.error} />
        </Section>
      </div>
      <PageActions
        summary={
          <div className="flex flex-col gap-1">
            {unchanged && current.data ? (
              <span>{PROMPT_COPY.unchangedHint(latestNumber, latestNumber + 1)}</span>
            ) : loaded !== null && loaded !== latestNumber ? (
              <span>{PROMPT_COPY.startedFrom(loaded, latestNumber + 1)}</span>
            ) : null}
            <ErrorMessage error={save.error} />
          </div>
        }
      >
        {unchanged ? (
          <Button size="lg" onClick={() => router.push(`/projects/${projectId}/data`)}>
            {PROMPT_COPY.next}
          </Button>
        ) : (
          <Button
            size="lg"
            onClick={() => void submit().catch(() => undefined)}
            disabled={empty || save.isPending}
          >
            {save.isPending ? PROMPT_COPY.saving : current.data ? PROMPT_COPY.saveVersion : PROMPT_COPY.save}
          </Button>
        )}
      </PageActions>
    </div>
  )
}
