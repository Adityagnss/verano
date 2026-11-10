/**
 * The guided path: the seven steps with a done / current mark in the sidebar, in order. Names and
 * hints come from `nav.ts` (the single source), so a rename happens in one place. `segment` is
 * the route under /projects/[projectId]/.
 */
import { PROJECT_NAV } from "./nav"

export type StepKey = "keys" | "prompt" | "data" | "tests" | "run" | "results" | "improve"

export type StepDefinition = {
  key: StepKey
  label: string
  hint: string
  segment: string
  available: boolean
}

export const STEPS: StepDefinition[] = PROJECT_NAV.filter((entry) => entry.guided).map((entry) => ({
  key: entry.key as StepKey,
  label: entry.label,
  hint: entry.subtitle,
  segment: entry.segment,
  available: entry.available,
}))
