/**
 * The signature moment: six nodes (Keys to Improve) joined by animated beams. A beam runs only between two
 * finished nodes. Each node links to its page. Under 768px it becomes a vertical timeline without beams.
 */
"use client"

import { Check } from "lucide-react"
import Link from "next/link"
import { createRef, useMemo, useRef, type RefObject } from "react"

import { useBreakpoint } from "@/components/common/use-breakpoint"
import { AnimatedBeam } from "@/components/ui/animated-beam"
import { cn } from "@/lib/utils"

import { PIPELINE, type NodeKey, type NodeState } from "./home-logic"

const STATE_TEXT: Record<NodeState, string> = { done: "Done", current: "Up next", todo: "To do" }

function Dot({ state, index }: { state: NodeState; index: number }) {
  return (
    <span
      className={cn(
        "flex size-12 items-center justify-center rounded-full text-sm font-semibold ring-2",
        state === "done" && "bg-success-soft text-success-strong ring-success",
        state === "current" && "bg-lagoon ring-lagoon text-white",
        state === "todo" && "bg-card text-text-muted ring-border",
      )}
    >
      {state === "done" ? <Check className="size-5" aria-hidden /> : index + 1}
    </span>
  )
}

export function Pipeline({ base, states }: { base: string; states: Record<NodeKey, NodeState> }) {
  const { atLeast } = useBreakpoint()
  const wide = atLeast("md")
  const container = useRef<HTMLDivElement>(null)
  const refs = useMemo(() => PIPELINE.map(() => createRef<HTMLSpanElement>()), [])

  if (!wide) {
    return (
      <ol aria-label="Your progress" className="flex flex-col">
        {PIPELINE.map((node, i) => (
          <li key={node.key} className="relative flex gap-4 pb-6 last:pb-0">
            {i < PIPELINE.length - 1 ? (
              <span
                aria-hidden
                className={cn(
                  "absolute top-12 bottom-0 left-6 w-0.5 -translate-x-1/2",
                  states[node.key] === "done" && states[PIPELINE[i + 1].key] === "done"
                    ? "bg-success"
                    : "bg-border",
                )}
              />
            ) : null}
            <Link
              href={`${base}/${node.segment}`}
              className="flex min-h-12 items-center gap-4 rounded-lg"
              aria-label={`${node.label}: ${STATE_TEXT[states[node.key]]}`}
            >
              <Dot state={states[node.key]} index={i} />
              <span className="flex flex-col">
                <span className="font-medium">{node.label}</span>
                <span className="text-text-secondary text-xs">{STATE_TEXT[states[node.key]]}</span>
              </span>
            </Link>
          </li>
        ))}
      </ol>
    )
  }

  return (
    <div ref={container} className="relative">
      <ol aria-label="Your progress" className="relative z-10 flex items-start justify-between gap-2">
        {PIPELINE.map((node, i) => (
          <li key={node.key} className="min-w-0 flex-1">
            <Link
              href={`${base}/${node.segment}`}
              aria-label={`${node.label}: ${STATE_TEXT[states[node.key]]}`}
              className="flex flex-col items-center gap-2 rounded-lg py-1 text-center"
            >
              <span ref={refs[i]} className="rounded-full">
                <Dot state={states[node.key]} index={i} />
              </span>
              <span className="text-sm font-medium">{node.label}</span>
              <span className="text-text-secondary text-xs">{STATE_TEXT[states[node.key]]}</span>
            </Link>
          </li>
        ))}
      </ol>
      {PIPELINE.slice(0, -1).map((node, i) =>
        states[node.key] === "done" && states[PIPELINE[i + 1].key] === "done" ? (
          <AnimatedBeam
            key={node.key}
            containerRef={container as RefObject<HTMLElement | null>}
            fromRef={refs[i]}
            toRef={refs[i + 1]}
            pathColor="#22804a"
            pathOpacity={0.35}
            gradientStartColor="#22804a"
            gradientStopColor="#2563eb"
            duration={4}
            delay={i * 0.4}
          />
        ) : null,
      )}
    </div>
  )
}
