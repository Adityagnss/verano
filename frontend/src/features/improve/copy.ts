/** User-facing text for the Improve step. */
export const IMPROVE_COPY = {
  title: "Improve the prompt",
  subtitle:
    "Verano looks at why test cases failed, writes 3 better prompts, tests them, and checks the best one on test cases it has never seen (the held-back part). Only the part set aside for improving is used to write them.",
  none: "Run an experiment and wait for its results first (steps 5 and 6).",
  experiment: "Improve from",
  start: "Find what's failing and suggest fixes",
  startHint: "Costs a few model calls plus the candidate test runs, on the same models you tested.",
  stages: {
    analyzing: "Looking at the failures…",
    testing: "Testing 3 candidates on the improving cases…",
    confirming: "Checking the best candidate on held-back cases…",
    done: "Done",
    failed: "Stopped",
  } as Record<string, string>,
  clustersHeading: "Why cases fail",
  cases: (n: number) => `${n} ${n === 1 ? "case" : "cases"}`,
  candidatesHeading: "Candidates",
  outcome: {
    pending: "Testing",
    better: "Better",
    not_better: "Not better",
    accepted: "Accepted",
    rejected: "Rejected",
  } as Record<string, string>,
  optimizeScore: "Quality on improving cases",
  current: "current",
  holdoutHeading: "Check on held-back cases",
  holdout: (current: string, candidate: string) => `Current prompt ${current} → best candidate ${candidate}`,
  accept: "Accept as new version",
  accepted: "Saved as a new prompt version.",
  nothingToAccept: "Nothing to accept yet.",
}
