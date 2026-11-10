/**
 * `useBreakpoint()`: which Tailwind width band the window is in, so a component can change what
 * it renders (not just how it is styled). Prefer CSS classes (`lg:flex`) when styling is enough.
 *
 *   const { current, atLeast } = useBreakpoint()
 *   atLeast("lg")   // true from 1024px up
 *
 * Bands match Tailwind: sm 640, md 768, lg 1024, xl 1280, 2xl 1536. On the server and during the
 * first client render it reports "base" (narrowest), so markup matches and then updates.
 */
"use client"

import { useSyncExternalStore } from "react"

export const BREAKPOINTS = { sm: 640, md: 768, lg: 1024, xl: 1280, "2xl": 1536 } as const
export type BreakpointName = "base" | keyof typeof BREAKPOINTS

const ORDER: BreakpointName[] = ["base", "sm", "md", "lg", "xl", "2xl"]

export function breakpointForWidth(width: number): BreakpointName {
  let found: BreakpointName = "base"
  for (const name of Object.keys(BREAKPOINTS) as (keyof typeof BREAKPOINTS)[]) {
    if (width >= BREAKPOINTS[name]) found = name
  }
  return found
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("resize", onChange)
  return () => window.removeEventListener("resize", onChange)
}

export function useBreakpoint(): {
  current: BreakpointName
  atLeast: (name: keyof typeof BREAKPOINTS) => boolean
} {
  const current = useSyncExternalStore(
    subscribe,
    () => breakpointForWidth(window.innerWidth),
    () => "base" as BreakpointName,
  )
  return { current, atLeast: (name) => ORDER.indexOf(current) >= ORDER.indexOf(name) }
}
