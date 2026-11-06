/**
 * "Add more checks" on the Test Cases step: three tabs (ready-made judges, rules, your own code).
 * Adding appends to the current checks and saves a new evaluator-set version, like any edit there.
 */
"use client"

import { useState } from "react"
import { toast } from "sonner"

import { ErrorMessage } from "@/components/common/error-message"
import { Section } from "@/components/common/section"
import type { EvaluatorConfigIn, EvaluatorSetVersionOut } from "@/lib/api/types"
import { cn } from "@/lib/utils"
import { useEditEvaluators } from "@/features/tests/hooks"

import { CHECKS_COPY } from "../copy"
import { currentChecks } from "../domain"
import { CodeEditor } from "./code-editor"
import { JudgeGallery } from "./judge-gallery"
import { RulePicker } from "./rule-picker"

const TABS = ["judges", "rules", "code"] as const
type Tab = (typeof TABS)[number]

export type AddCheck = (check: EvaluatorConfigIn, title: string) => Promise<void>

export function CheckLibrary({
  projectId,
  versionId,
  set,
  frozen,
}: {
  projectId: string
  versionId: string
  set: EvaluatorSetVersionOut
  frozen: boolean
}) {
  const [tab, setTab] = useState<Tab>("judges")
  const edit = useEditEvaluators(projectId, versionId)
  const add: AddCheck = async (check, title) => {
    try {
      await edit.mutateAsync([...currentChecks(set), check])
      toast.success(CHECKS_COPY.added(title))
    } catch {
      // the error is shown below
    }
  }
  const common = { projectId, set, frozen, busy: edit.isPending, add }
  return (
    <Section title={CHECKS_COPY.heading} description={CHECKS_COPY.hint}>
      <div role="tablist" aria-label={CHECKS_COPY.tabsLabel} className="border-border flex gap-1 border-b">
        {TABS.map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            id={`checks-tab-${key}`}
            aria-selected={tab === key}
            aria-controls="checks-panel"
            tabIndex={tab === key ? 0 : -1}
            onClick={() => setTab(key)}
            onKeyDown={(event) => {
              const move = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0
              if (!move) return
              const next = TABS[(TABS.indexOf(key) + move + TABS.length) % TABS.length]
              setTab(next)
              document.getElementById(`checks-tab-${next}`)?.focus()
            }}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm font-medium",
              tab === key
                ? "border-lagoon text-foreground"
                : "text-text-secondary hover:text-foreground border-transparent",
            )}
          >
            {CHECKS_COPY.tabs[key]}
          </button>
        ))}
      </div>
      <div
        id="checks-panel"
        role="tabpanel"
        aria-labelledby={`checks-tab-${tab}`}
        className="flex flex-col gap-4"
      >
        {frozen ? <p className="text-text-secondary text-sm">{CHECKS_COPY.frozen}</p> : null}
        {tab === "judges" ? <JudgeGallery {...common} /> : null}
        {tab === "rules" ? <RulePicker {...common} /> : null}
        {tab === "code" ? <CodeEditor {...common} /> : null}
        <ErrorMessage error={edit.error} />
      </div>
    </Section>
  )
}
