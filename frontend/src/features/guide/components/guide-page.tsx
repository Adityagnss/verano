/**
 * The Prompting guide index: one card per section. Each section is its own page
 * (guide/[section]) so nobody has to scroll one giant page. The text comes from the server's
 * Markdown (backend/app/modules/assistant/prompts/prompt_guide.md) and is only reorganised.
 */
"use client"

import { ArrowRight } from "lucide-react"
import Link from "next/link"

import { CopyButton } from "@/components/common/copy-button"
import { ErrorMessage } from "@/components/common/error-message"
import { PageIntro } from "@/components/common/page-intro"
import { buttonVariants } from "@/components/ui/button"
import { ALL_PROJECT_PAGES } from "@/lib/nav"
import { cn } from "@/lib/utils"

import { pageAsMarkdown } from "../copy-text"
import { usePromptNotes } from "../hooks"
import { GUIDE_SECTIONS } from "../sections"
import { DIAGRAM_LABELS } from "./diagrams"

const PAGE = ALL_PROJECT_PAGES.find((p) => p.key === "guide")!

export function GuidePage({ projectId }: { projectId: string }) {
  const notes = usePromptNotes()
  const base = `/projects/${projectId}/guide`
  return (
    <div className="mx-auto flex w-full max-w-5xl min-w-0 flex-col gap-6">
      <PageIntro
        storageKey="guide"
        title={PAGE.label}
        what="Techniques, templates and a checklist for writing prompts, each marked as measured, common practice or worth a test."
        whenToUse="you are writing a prompt or deciding what to try next"
        youGet="short pages you can read in minutes, and templates you can copy"
        primaryAction={
          <Link href={`${base}/${GUIDE_SECTIONS[0].slug}`} className={buttonVariants({ size: "lg" })}>
            Start reading
          </Link>
        }
        learnMore="guide"
      />
      <ErrorMessage error={notes.error} />
      {notes.data ? (
        <div>
          <CopyButton
            text={() => pageAsMarkdown(notes.data, DIAGRAM_LABELS)}
            label="Copy the whole guide"
            doneLabel="Copied to clipboard"
            size="default"
            variant="outline"
            notify="Guide copied as Markdown"
          />
        </div>
      ) : null}
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {GUIDE_SECTIONS.map((section, index) => (
          <li key={section.slug}>
            <Link
              href={`${base}/${section.slug}`}
              className={cn(
                "bg-card ring-border hover:bg-subtle focus-visible:ring-ring flex h-full min-h-10 flex-col gap-1.5 rounded-xl p-4 ring-1 outline-none focus-visible:ring-2",
              )}
            >
              <span className="text-text-muted text-xs tabular-nums">Part {index + 1}</span>
              <span className="flex items-center justify-between gap-2 font-semibold">
                {section.title}
                <ArrowRight className="text-lagoon-strong size-4 shrink-0" aria-hidden />
              </span>
              <span className="text-text-secondary text-sm">{section.summary}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
