/** Pure rules for project Home: which pipeline nodes are done, which one is current, and the single best next step. */
export type NodeKey = "keys" | "prompt" | "tests" | "run" | "results" | "improve"
export type NodeState = "done" | "current" | "todo"

export type Completion = {
  keys: boolean
  prompt: boolean
  data: boolean
  tests: boolean
  run: boolean
  results: boolean
  improve: boolean
}

export const PIPELINE: { key: NodeKey; label: string; segment: string }[] = [
  { key: "keys", label: "Keys", segment: "keys" },
  { key: "prompt", label: "Prompt", segment: "prompt" },
  { key: "tests", label: "Cases", segment: "tests" },
  { key: "run", label: "Run", segment: "run" },
  { key: "results", label: "Results", segment: "results" },
  { key: "improve", label: "Improve", segment: "improve" },
]

export const EMPTY_COMPLETION: Completion = {
  keys: false,
  prompt: false,
  data: false,
  tests: false,
  run: false,
  results: false,
  improve: false,
}

/** The first unfinished node is current; later ones are to do. */
export function nodeStates(done: Completion): Record<NodeKey, NodeState> {
  let currentTaken = false
  const out = {} as Record<NodeKey, NodeState>
  for (const node of PIPELINE) {
    if (done[node.key]) out[node.key] = "done"
    else if (!currentTaken) {
      out[node.key] = "current"
      currentTaken = true
    } else out[node.key] = "todo"
  }
  return out
}

export type NextStep = { segment: string; title: string; why: string; action: string }

const NEXT: Record<NodeKey, NextStep> = {
  keys: {
    segment: "keys",
    title: "Connect a model provider",
    why: "Verano needs a key to call the models you want to compare. Keys are stored encrypted.",
    action: "Connect models",
  },
  prompt: {
    segment: "prompt",
    title: "Write your prompt",
    why: "The prompt is what every model will be tested on.",
    action: "Write your prompt",
  },
  tests: {
    segment: "tests",
    title: "Approve your test cases",
    why: "Test cases are the inputs and answers the models are scored on. Check them before you run.",
    action: "Approve test cases",
  },
  run: {
    segment: "run",
    title: "Run the test",
    why: "Run every model on your test cases to see quality, cost and speed.",
    action: "Run the test",
  },
  results: {
    segment: "results",
    title: "Wait for the run to finish",
    why: "Results appear as soon as one run has finished and been scored.",
    action: "See the run",
  },
  improve: {
    segment: "improve",
    title: "Improve the prompt",
    why: "Find what fails and test better versions. A version only counts as better when it wins on cases it has not seen.",
    action: "Improve the prompt",
  },
}

export function nextStep(done: Completion): NextStep | null {
  const current = PIPELINE.find((n) => !done[n.key])
  return current ? NEXT[current.key] : null
}

export const DONE_STEP: NextStep = {
  segment: "improve",
  title: "Keep improving",
  why: "Every step is done. Try another prompt version, or watch how your models trend over time.",
  action: "Improve the prompt again",
}

export type CardState = "not started" | "ready" | "in progress"
