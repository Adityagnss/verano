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
    'Same answer: how alike the answers themselves are across runs. Separate from consistency, and from "same configuration", which only says two experiments were set up identically.',
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
    stability: "Same answer",
    latency: "Avg. time",
    cost: "Cost",
    perCall: "Per call",
    failed: "Failed calls",
  },
  consistencyHint: "Share of test cases where every run got the same pass/fail result. Needs 2+ runs.",
  stabilityHint:
    "How alike the answers are across repeated runs of the same test case: the largest group of matching answers out of the runs, averaged over cases. Matching means the same text (spacing ignored, or the same JSON). Needs 2+ runs. This is separate from consistency, which compares pass/fail.",
  stability: (stable: number, compared: number) => `${stable} of ${compared} cases identical`,
  agreement: (model: string, same: number, runs: number) =>
    `${model}: same answer in ${same} of ${runs} runs`,
  unjudged: (count: number, total: number) =>
    `${count} of ${total} answers could not be judged. They are left out of quality and pass rate (never counted as passed), and each shows the judge's reason in its case below.`,
  scoreAgain: "Score again",
  scoreAgainCost: (calls: number | null, cost: string | null) =>
    `This asks the judge to score every answer again${calls ? ` (about ${calls} judge calls${cost ? `, about $${Number(cost).toFixed(4)}` : ""})` : ""}. The earlier scoring is kept.`,
  judgeLabel: "Judge model",
  judgeHint:
    "The model that scores the judged checks. It is kept with the checks, so scores from different judges are never compared directly.",
  judgeSuggested: "suggested",
  judgeSelf:
    "This model is also one of the models being tested. A model tends to favour its own answers, so pick another if you can.",
  judgeNone: "Choose a judge",
  scoreAgainConfirm: "Score again now",
  scoreAgainCancel: "Cancel",
  notJudged: "Not judged",
  notJudgedWhy: "This check could not be scored, so the answer is left out of the numbers:",
  judgedCount: (judged: number, total: number) => `${judged} of ${total} judged`,
  rerun: "Re-run with same settings",
  rerunning: "Starting…",
  rerunHint: "Starts a new experiment with the same prompt, test cases, models and settings.",
  replication: (same: number, compared: number, name: string) =>
    `Same answer in ${same} of ${compared} calls as "${name}".`,
  replicationSkipped: (count: number) =>
    `${count} calls had nothing to compare with (failed, or not in the other run).`,
  versionChangedWithin:
    "The provider answered this model under more than one version in this experiment, so differences between runs may come from the provider.",
  versionChangedBetween: (model: string, before: string[], after: string[]) =>
    `${model}: the provider's model changed since that run (${before.join(", ")} → ${after.join(", ")}). Different answers may come from that change, not from your settings.`,
  replicationNote:
    "A fixed seed makes matching answers more likely, but providers can change models, hardware or routing, so this is a check and not a guarantee.",
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
