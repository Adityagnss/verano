/**
 * The guided path (DEVELOPMENT.md C1): the seven steps shown in the stepper, in order.
 * `hint` is the one-line "what happens here" shown under each step. `segment` is the route
 * under /projects/[projectId]/; `available` is false for steps whose screens aren't built,
 * which the stepper shows as upcoming but not clickable.
 */
export type StepKey = "keys" | "prompt" | "data" | "tests" | "run" | "results" | "improve"

export type StepDefinition = {
  key: StepKey
  label: string
  hint: string
  segment: string
  available: boolean
}

export const STEPS: StepDefinition[] = [
  { key: "keys", label: "Keys", hint: "Connect providers", segment: "keys", available: true },
  { key: "prompt", label: "Prompt", hint: "Write what to test", segment: "prompt", available: true },
  { key: "data", label: "Your Data", hint: "Optional examples", segment: "data", available: true },
  { key: "tests", label: "Test Cases", hint: "Approve what is checked", segment: "tests", available: true },
  { key: "run", label: "Run", hint: "Run on each model", segment: "run", available: true },
  { key: "results", label: "Results", hint: "Compare the models", segment: "results", available: true },
  { key: "improve", label: "Improve", hint: "Fix what fails", segment: "improve", available: true },
]
