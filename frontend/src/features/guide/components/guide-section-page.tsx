/** One section of the Prompting guide, with a contents list and previous/next links. */
"use client"

import { ChevronLeft, ChevronRight } from "lucide-react"
import Link from "next/link"

import { ErrorMessage } from "@/components/common/error-message"
import { Markdown, headingsOf } from "@/components/common/markdown"
import { Skeleton } from "@/components/ui/skeleton"
import { buttonVariants } from "@/components/ui/button"

import { usePromptNotes } from "../hooks"
import { findSection, neighbours, sectionMarkdown } from "../sections"
import { DIAGRAMS } from "./diagrams"

export function GuideSectionPage({ projectId, section }: { projectId: string; section: string }) {
  const notes = usePromptNotes()
  const found = findSection(section)
  const base = `/projects/${projectId}/guide`
  if (!found) {
    return (
      <div className="mx-auto flex max-w-xl flex-col gap-3">
        <h1 className="text-xl font-semibold">This guide page does not exist</h1>
        <Link href={base} className={buttonVariants({ size: "lg" })}>
          Back to the guide
        </Link>
      </div>
    )
  }
  const { previous, next } = neighbours(found)
  const source = notes.data ? sectionMarkdown(notes.data, found) : ""
  const headings = headingsOf(source)
  const toc =
    headings.length > 1 ? (
      <ul className="flex flex-col gap-1 text-sm">
        {headings.map((h) => (
          <li key={h.id}>
            <a
              href={`#${h.id}`}
              className="text-text-secondary hover:text-foreground block min-h-10 rounded-md px-2 py-2 lg:min-h-0 lg:py-1.5"
            >
              {h.title}
            </a>
          </li>
        ))}
      </ul>
    ) : null
  return (
    <div className="mx-auto flex w-full max-w-6xl min-w-0 flex-col gap-5">
      <nav aria-label="Breadcrumb" className="text-text-secondary text-sm">
        <Link href={base} className="hover:text-foreground underline-offset-2 hover:underline">
          Prompting guide
        </Link>{" "}
        / {found.title}
      </nav>
      <h1 className="text-2xl font-semibold">{found.title}</h1>
      <div className="grid min-w-0 gap-6 lg:grid-cols-[14rem_minmax(0,1fr)]">
        {toc ? (
          <>
            <details className="bg-card ring-border rounded-xl px-3 ring-1 lg:hidden">
              <summary className="flex min-h-10 cursor-pointer items-center text-sm font-medium">
                On this page
              </summary>
              <div className="pb-2">{toc}</div>
            </details>
            <nav aria-label="On this page" className="hidden lg:block">
              <div className="sticky top-20">{toc}</div>
            </nav>
          </>
        ) : (
          <div className="hidden lg:block" />
        )}
        <article className="bg-card ring-border min-w-0 overflow-x-auto rounded-xl p-4 ring-1 sm:p-6 [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_table]:block [&_table]:max-w-full [&_table]:overflow-x-auto">
          <ErrorMessage error={notes.error} />
          {notes.isPending ? <Skeleton className="h-64 w-full" /> : null}
          {notes.data ? <Markdown source={source} diagrams={DIAGRAMS} /> : null}
        </article>
      </div>
      <nav aria-label="Guide pages" className="flex flex-wrap justify-between gap-3">
        {previous ? (
          <Link
            href={`${base}/${previous.slug}`}
            className={buttonVariants({ variant: "outline", size: "lg" })}
          >
            <ChevronLeft aria-hidden /> Previous: {previous.title}
          </Link>
        ) : (
          <span />
        )}
        {next ? (
          <Link href={`${base}/${next.slug}`} className={buttonVariants({ size: "lg" })}>
            Next: {next.title} <ChevronRight aria-hidden />
          </Link>
        ) : (
          <Link href={base} className={buttonVariants({ size: "lg" })}>
            Back to the guide
          </Link>
        )}
      </nav>
    </div>
  )
}
