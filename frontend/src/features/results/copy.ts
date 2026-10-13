/** User-facing text for the Results step. */
import { formatMs } from "@/lib/format"

export const signedPercent = (value: number) => `${value >= 0 ? "+" : ""}${Math.round(value * 100)}%`

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
  candidateTest: (strategy: string) =>
    `This is Improve's test of the candidate “${strategy}”, on part of your test cases.`,
  candidateUse: "To use that prompt, save it as a version and test it on all test cases.",
  candidateButton: "Save and test on all cases",
  unfairTitle: "Not a fair comparison, so no model is ranked on quality or pass rate.",
  unfairAdvice:
    "Run the models again with the same number of runs and the same randomness (Run step: pick Repeatable) to rank them.",
  broken: (model: string, failed: number, total: number) =>
    `${model}: ${failed} of ${total} calls failed, so its scores are not meaningful. Open a failed case below to see the error.`,
  tableHeading: "All models side by side",
  tableHint: "The best value in each column is highlighted.",
  loadingCases: "Loading test cases…",
  none: "No finished experiment yet. Start one in step 5.",
  experiment: "Experiment",
  scoring: "Scoring…",
  scoringAgain: "Scoring again… the numbers below are from the earlier pass until it finishes.",
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
  vsBest: "Compared with the best",
  vsBestHint:
    "How each model compares with the best one on quality, test case by test case. A clear difference means the gap is larger than chance would explain; otherwise the ranking could be luck.",
  bestOnQuality: "Best on quality",
  labels: {
    "clear difference": "clearly behind",
    "no clear difference": "no clear difference",
    "too few cases": "too few cases to tell",
  } as Record<string, string>,
  comparisonLines: (
    cases: number,
    difference: number | null,
    low: number | null,
    high: number | null,
    level: number,
  ) =>
    `${cases} test cases compared. Quality difference ${difference === null ? "—" : signedPercent(difference)}` +
    (low !== null && high !== null
      ? `, ${Math.round(level * 1000) / 10}% interval ${signedPercent(low)} to ${signedPercent(high)}.`
      : ". Too few cases for an interval."),
  comparisonPass: (difference: number | null, p: number | null, onlyFirst: number, onlySecond: number) =>
    `Pass rate difference ${difference === null ? "—" : signedPercent(difference)}; ${onlyFirst} cases only this one passed, ${onlySecond} only the other${p === null ? "" : ` (exact test p = ${p < 0.001 ? "<0.001" : p.toFixed(3)})`}.`,
  comparisonLeftOut: (first: number, second: number) =>
    `${first + second} cases were left out because one side could not be judged on them.`,
  rerunQuality: (label: string) => `Scores moved between the runs: ${label}.`,
  seeJudge: "What the judge saw",
  hideJudge: "Hide what the judge saw",
  judgeNoCalls: "The judge was not asked anything about this answer (the other checks need no judge).",
  judgeCall: (n: number, total: number, evaluator: string | null) =>
    `Request ${n} of ${total}${evaluator ? ` · ${evaluator.replaceAll("_", " ")}` : ""}`,
  judgePreview: "(preview, not part of the results)",
  judgeReply: "The judge replied",
  judgeFailed: "The call failed",
  judgingHeading: "How the judge scores",
  judgingHint:
    "The judge reads the test case, the answer and these criteria. Change them or the judge model, try it on one answer, then score again: the results of the earlier scoring are kept, and scores from different criteria or judges are never mixed.",
  criteria: "Criteria",
  criteriaHint: "In words, what a good answer is. {rubric} stands for each test case's own rubric.",
  steps: "Evaluation steps (optional)",
  stepsHint:
    "One step per line, at most 10. When given, they replace the criteria: the judge follows exactly these.",
  tryHeading: "Try the judge on one answer",
  tryPick: "Answer to try",
  tryRun: "Try the judge",
  trying: "Asking the judge…",
  tryCost: (calls: number, cost: string | null) =>
    `This makes ${calls} judge ${calls === 1 ? "call" : "calls"}${cost ? ` (about $${Number(cost).toFixed(4)})` : " (price unknown)"}. Nothing is scored or changed.`,
  tryResult: (value: number, passed: boolean) =>
    `Score ${Math.round(value * 100)}% · ${passed ? "pass" : "fail"}`,
  scoreWithChanges: "Score again with these changes",
  nothingChanged: "Nothing changed yet.",
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
