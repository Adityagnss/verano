/**
 * The Prompt guide: the prompting notes as a readable page, with a table of contents. The
 * notes are one Markdown file on the server (backend/app/modules/assistant/prompts/
 * technique_notes.md) that the Improve step reads too, so people and Improve always see the
 * same advice.
 */
"use client"

import Link from "next/link"

import { ErrorMessage } from "@/components/common/error-message"
import { Markdown, headingsOf } from "@/components/common/markdown"
import { Section } from "@/components/common/section"
import { Skeleton } from "@/components/ui/skeleton"

import { usePromptNotes } from "../hooks"
import { DIAGRAMS } from "./diagrams"

export function GuidePage({ projectId }: { projectId: string }) {
  const notes = usePromptNotes()
  const headings = notes.data ? headingsOf(notes.data) : []
  return (
    <div className="mx-auto flex w-full max-w-[80rem] flex-col gap-6">
      <header className="from-lagoon-soft to-card ring-lagoon/15 flex flex-col gap-3 rounded-2xl bg-gradient-to-br px-6 py-7 ring-1 sm:px-8">
        <p className="text-lagoon-strong text-sm font-medium">Prompt guide</p>
        <h2 className="max-w-[40rem] text-2xl leading-tight font-semibold sm:text-[2rem]">
          Notes on prompting: what helps, what does not, and how to prove it
        </h2>
        <p className="text-text-secondary max-w-[46rem] text-[0.95rem] leading-relaxed">
          Short notes taken from a measured prompt-engineering tutorial and the studies it cites. Use them to
          decide what to try, then let a run tell you whether it helped. The Improve step reads these same
          notes when it writes better prompts for you.
        </p>
        <div className="flex flex-wrap gap-3 pt-1 text-sm">
          <Link
            href={`/projects/${projectId}/prompt`}
            className="bg-primary text-primary-foreground rounded-lg px-4 py-2 font-medium"
          >
            Write a prompt
          </Link>
          <Link
            href={`/projects/${projectId}/improve`}
            className="text-lagoon-strong ring-lagoon/30 bg-card rounded-lg px-4 py-2 font-medium ring-1"
          >
            Improve my prompt
          </Link>
        </div>
      </header>
      <div className="grid gap-6 lg:grid-cols-[14rem_minmax(0,1fr)]">
        <nav aria-label="On this page" className="hidden lg:block">
          <ul className="sticky top-20 flex flex-col gap-1 text-sm">
            {headings.map((heading) => (
              <li key={heading.id}>
                <a
                  href={`#${heading.id}`}
                  className="text-text-secondary hover:text-foreground block rounded-md px-2 py-1.5"
                >
                  {heading.title}
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <Section title="Prompting notes">
          <ErrorMessage error={notes.error} />
          {notes.isPending ? <Skeleton className="h-64 w-full" /> : null}
          {notes.data ? <Markdown source={notes.data.replace(/^# .*\n/, "")} diagrams={DIAGRAMS} /> : null}
        </Section>
      </div>
    </div>
  )
}
