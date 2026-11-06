/** User-facing text for the Run step. */
export const RUN_COPY = {
  title: "Run your test cases on each model",
  subtitle:
    "Every test case is sent to every chosen model. Run a model more than once to see how consistent it is. You see the cost before anything starts.",
  howItWorks: [
    "Every approved test case is sent to every model you include.",
    "Run a model 2+ times to see how consistent it is.",
    "Check the cost preview and set a budget cap if you like.",
    "Results are scored automatically when the run finishes.",
    "You set the model, prompt, test cases and settings. Verano locks and records the versions, a fingerprint of the configuration, cost, tokens and time. The provider controls the model snapshot, hardware and routing, which Verano records but cannot guarantee.",
    "Runs set up the same way get the same fingerprint, so Results can tell you when two experiments are replicable. That is not a promise of identical answers.",
  ],
  modelsHeading: "Choose models and settings",
  versionLabel: "Prompt version to test",
  versionLatest: (n: number) => `Version ${n} (latest)`,
  versionOption: (n: number, note: string | null | undefined) => `Version ${n}${note ? `: ${note}` : ""}`,
  versionHint: "Test any saved version on the same test cases, then compare them on the Dashboard.",
  randomnessLabel: "Randomness",
  randomness: {
    repeatable: {
      label: "Repeatable",
      hint: "Temperature 0 and a fixed seed, where the model accepts them. Best for comparing models and prompt versions.",
    },
    default: {
      label: "Model's own default",
      hint: "The provider's usual settings: more varied answers, closer to how a chat app behaves.",
    },
    custom: "Set by hand per model below.",
  },
  replicabilityHint:
    "Repeatable makes answers as alike as the provider allows, but it is not a guarantee. To check: after the run, open Results and press Re-run with same settings; it compares the answers call by call.",
  modelsHint: "The models you ticked in step 1. Untick any you want to leave out of this run.",
  previewHint: "Nothing is spent until you press Start experiment.",
  runningHint: "Updates live while the models answer.",
  notApproved: "Approve your test cases first (step 4).",
  noModels: "Pick the models to compare in step 1.",
  columns: { model: "Model", runs: "Runs", temperature: "Temperature", maxTokens: "Max reply tokens" },
  modelsHint2:
    "Temperature 0 and a fixed seed are filled in where a model accepts them, so a run can be repeated. Clear a box to use the provider's own default.",
  include: "Include",
  advanced: "Advanced",
  runsAll: "Answers per test case, for every model",
  runsAllHint:
    "Each model answers each case this many times, so the pass rate and how consistent it is can be compared fairly. 1 to 5.",
  expert: "Expert settings: runs, temperature, maximum length and more, model by model",
  summaryHeading: "What will run",
  summary: (cases: number, models: string, version: string, judge: string | null) =>
    `${cases} test cases on ${models}, with ${version}${judge ? `, judged by ${judge}` : ""}.`,
  advancedSet: (count: number) => (count === 0 ? "Advanced" : `Advanced (${count} set)`),
  advancedHint:
    "Only settings this model accepts are shown. Leave a box empty to use the provider's default.",
  fields: {
    seed: {
      label: "Seed",
      hint: "Makes repeats more likely to match, but providers don't guarantee it. With several runs, run 2 uses seed + 1, run 3 seed + 2, and so on, so repeating the experiment sends every run the same seed again.",
    },
    top_p: {
      label: "Top P",
      hint: "Only the most likely words that add up to this share are considered (0 to 1).",
    },
    top_k: { label: "Top K", hint: "Only this many of the most likely words are considered." },
    frequency_penalty: {
      label: "Frequency penalty",
      hint: "Discourages repeating the same words (-2 to 2).",
    },
    presence_penalty: { label: "Presence penalty", hint: "Encourages new topics (-2 to 2)." },
    stop: {
      label: "Stop sequences",
      hint: "One per line, up to 4. The reply ends where one appears. Write \\n for a new line. Careful: they can cut a JSON answer short.",
    },
  },
  unsupported: "Not supported by this model",
  budget: "Budget cap (USD, optional)",
  budgetHint: "The run stops when it has spent this much. Finished results are kept.",
  previewHeading: "Cost preview",
  calls: (calls: number, cases: number) => `${calls} calls (${cases} test cases)`,
  generation: "Model calls",
  judge: (calls: number) => `Scoring (${calls} judge calls)`,
  judgeModel: (name: string) => `Judge: ${name}`,
  scoringShare: (percent: number) =>
    `Scoring is about ${percent}% of this run. Identical answers are judged only once.`,
  total: "Estimated total",
  unknown: "Price unknown",
  busy: "An experiment is still running. Start another when it has finished.",
  start: "Start experiment",
  starting: "Starting…",
  runningHeading: "Latest experiment",
  status: {
    draft: "Draft",
    planned: "Planned",
    running: "Running",
    paused: "Paused",
    evaluating: "Scoring",
    completed: "Finished",
    cancelled: "Stopped",
    failed: "Failed",
  } as Record<string, string>,
  progress: (done: number, total: number) => `${done} / ${total}`,
  failedCalls: (count: number) => `${count} failed`,
  cancel: "Stop",
  scoringBar: "Scoring the answers",
  scoringDone: (done: number, total: number) => `${done} of ${total} answers`,
  timeLeft: (seconds: number) =>
    seconds < 90 ? `about ${seconds} s left` : `about ${Math.round(seconds / 60)} min left`,
  results: "See results",
}
