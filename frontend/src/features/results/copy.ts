/** User-facing text for the Results step. */
import { formatMs } from "@/lib/format"

export const RESULTS_COPY = {
  title: "See how each model did",
  subtitle:
    "Quality and pass rate come from the scoring you approved in step 4. Plain averages over all test cases.",
  howItWorks: [
    "Quality: the average score of each answer (0–100%).",
    "Passed: share of test cases where every check passed.",
    "How consistent: same pass/fail across repeated runs (needs 2+ runs).",
    "Click any test case below to see every model's answer side by side.",
  ],
  tiles: { quality: "Best quality", passRate: "Most passed", cost: "Cheapest per call", speed: "Fastest" },
  tileNone: "—",
  broken: (model: string, failed: number, total: number) =>
    `${model}: ${failed} of ${total} calls failed, so its scores are not meaningful. Open a failed case below to see the error.`,
  tableHeading: "All models side by side",
  tableHint: "The best value in each column is highlighted.",
  loadingCases: "Loading test cases…",
  none: "No finished experiment yet. Start one in step 5.",
  experiment: "Experiment",
  scoring: "Scoring…",
  notScored: "This experiment is still being scored.",
  columns: {
    model: "Model",
    quality: "Quality",
    passRate: "Passed",
    consistency: "How consistent",
    latency: "Avg. time",
    cost: "Cost",
    perCall: "Per call",
    failed: "Failed calls",
  },
  consistencyHint: "Share of test cases where every run got the same pass/fail result. Needs 2+ runs.",
  chartTitle: "Passed test cases",
  casesHeading: "Test cases",
  failedOnly: "Only cases with a failure",
  expected: "Correct answer",
  rubric: "Grading criteria",
  run: (n: number) => `run ${n}`,
  pass: "Pass",
  fail: "Fail",
  export: "Export CSV",
  noCases: "No cases to show.",
  next: "Next: improve the prompt",
  ms: (value: number) => formatMs(value),
}
