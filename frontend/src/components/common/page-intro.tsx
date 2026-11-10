/**
 * `PageIntro`: how every page opens. The page name (the one <h1>), a sentence on what the page is,
 * "Use it when" and "You get" lines, ONE primary action and a "Learn more" link. It collapses to
 * a one-line header once the page has content (`hasContent`) or the person dismissed it; the
 * dismissal is remembered per `storageKey` in localStorage (failures are ignored). A collapsed
 * intro can be opened again with "Show help".
 *
 *   <PageIntro
 *     storageKey="results"
 *     title="Compare results"
 *     what="Quality, cost and speed for every model, side by side."
 *     whenToUse="after a test run has finished"
 *     youGet="a ranking you can trust and the cheapest model that is good enough"
 *     primaryAction={<Button>Run the test</Button>}
 *     learnMore="results"
 *     hasContent={runs.length > 0}
 *   />
 */
"use client"

import { ChevronDown, ChevronUp, ExternalLink } from "lucide-react"
import { AnimatePresence, motion } from "motion/react"
import { type ReactNode, useState, useSyncExternalStore } from "react"

import { Button } from "@/components/ui/button"
import { docsUrl } from "@/lib/nav"
import { cn } from "@/lib/utils"

const KEY_PREFIX = "verano.intro."

/** Dismissals for this tab, so collapsing still works when storage is blocked. */
const memory = new Set<string>()

function readDismissed(storageKey: string): boolean {
  if (memory.has(storageKey)) return true
  try {
    return window.localStorage.getItem(KEY_PREFIX + storageKey) === "1"
  } catch {
    return false
  }
}

const CHANGE_EVENT = "verano:intro-change"

function subscribe(onChange: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, onChange)
  window.addEventListener("storage", onChange)
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange)
    window.removeEventListener("storage", onChange)
  }
}

function writeDismissed(storageKey: string, value: boolean): void {
  if (value) memory.add(storageKey)
  else memory.delete(storageKey)
  try {
    if (value) window.localStorage.setItem(KEY_PREFIX + storageKey, "1")
    else window.localStorage.removeItem(KEY_PREFIX + storageKey)
  } catch {
    /* storage unavailable: the choice just is not remembered */
  }
  window.dispatchEvent(new Event(CHANGE_EVENT))
}

export type PageIntroProps = {
  /** The page's name (use the name from `src/lib/nav.ts`). */
  title: string
  /** One sentence: what this page is. */
  what: string
  /** Completes "Use it when ...". */
  whenToUse: string
  /** Completes "You get ...". */
  youGet: string
  /** The one main thing to do here. */
  primaryAction?: ReactNode
  /** Docs slug (see `docsUrl`). */
  learnMore: string
  /** Unique per page; remembers a dismissal. */
  storageKey: string
  /** True once the page has real content: the intro starts collapsed. */
  hasContent?: boolean
  className?: string
}

export function PageIntro({
  title,
  what,
  whenToUse,
  youGet,
  primaryAction,
  learnMore,
  storageKey,
  hasContent = false,
  className,
}: PageIntroProps) {
  const dismissed = useSyncExternalStore(
    subscribe,
    () => readDismissed(storageKey),
    () => false,
  )
  const [reopened, setReopened] = useState(false)

  const expanded = reopened || (!dismissed && !hasContent)

  function collapse() {
    setReopened(false)
    writeDismissed(storageKey, true)
  }
  function expand() {
    setReopened(true)
    writeDismissed(storageKey, false)
  }

  return (
    <header
      data-testid="page-intro"
      data-expanded={expanded}
      className={cn("border-border flex flex-col gap-4 border-b pb-5", className)}
    >
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
        <div className="min-w-0 flex-1 basis-64">
          <h1 className="text-xl leading-tight font-semibold sm:text-2xl">{title}</h1>
          {expanded ? null : <p className="text-text-secondary mt-1 text-sm">{what}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {expanded ? null : (
            <Button variant="ghost" size="sm" onClick={expand} aria-expanded={false} className="min-h-10">
              <ChevronDown aria-hidden /> Show help
            </Button>
          )}
          {primaryAction}
        </div>
      </div>
      <AnimatePresence initial={false}>
        {expanded ? (
          <motion.div
            key="details"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <div className="flex flex-col gap-3">
              <p className="text-text-secondary max-w-3xl text-[0.95rem] leading-relaxed">{what}</p>
              <dl className="grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-text-muted text-xs font-semibold tracking-wide uppercase">
                    Use it when
                  </dt>
                  <dd className="mt-0.5">{whenToUse}</dd>
                </div>
                <div>
                  <dt className="text-text-muted text-xs font-semibold tracking-wide uppercase">You get</dt>
                  <dd className="mt-0.5">{youGet}</dd>
                </div>
              </dl>
              <div className="flex flex-wrap items-center gap-3 text-sm">
                <a
                  href={docsUrl(learnMore)}
                  target="_blank"
                  rel="noreferrer"
                  className="text-lagoon-strong inline-flex min-h-10 items-center gap-1 font-medium underline"
                >
                  Learn more <ExternalLink className="size-3.5" aria-hidden />
                </a>
                <Button variant="ghost" size="sm" onClick={collapse} aria-expanded className="min-h-10">
                  <ChevronUp aria-hidden /> Hide help
                </Button>
              </div>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </header>
  )
}
