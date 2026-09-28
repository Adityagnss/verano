/**
 * The guided path (DEVELOPMENT.md C1): the seven steps shown in the stepper, in order.
 * `segment` is the route under /projects/[projectId]/; `available` is false for steps whose
 * screens arrive in later phases, which the stepper shows as upcoming but not clickable.
 */
export type StepKey = "keys" | "prompt" | "data" | "tests" | "run" | "results" | "improve"

export type StepDefinition = { key: StepKey; label: string; segment: string; available: boolean }

export const STEPS: StepDefinition[] = [
  { key: "keys", label: "Keys", segment: "keys", available: true },
  { key: "prompt", label: "Prompt", segment: "prompt", available: true },
  { key: "data", label: "Your Data", segment: "data", available: true },
  { key: "tests", label: "Test Cases", segment: "tests", available: true },
  { key: "run", label: "Run", segment: "run", available: true },
  { key: "results", label: "Results", segment: "results", available: false },
  { key: "improve", label: "Improve", segment: "improve", available: false },
]
