/** User-facing text for adding checks. */
export const CHECKS_COPY = {
  heading: "Add more checks",
  hint: "Pick a ready-made judge, a rule that needs no model, or write a small check of your own. Each one is added to the checks above.",
  tabs: { judges: "Ready-made judges", rules: "Rules", code: "Your own code" },
  tabsLabel: "Kind of check",
  frozen: "The test cases are approved, so the checks are fixed. Change the test cases to add checks.",
  added: (title: string) => `${title} added to your checks.`,
  already: "Already in your checks",
  add: "Add to my checks",
  adding: "Adding…",
  loading: "Loading…",
  judges: {
    intro:
      "A judge is a model that reads each answer and decides with the instruction shown. It can be wrong, so look at how often it agrees with people before you trust it.",
    empty: "No ready-made judges are available.",
    needs: (what: string) => `Needs ${what} in each test case, or the judge skips the case.`,
    passMark: (n: number) => `Passes at ${Math.round(n * 100)}% or more.`,
    instruction: "What the judge is told",
    cannot: "What it cannot tell",
    notMeasured: "Agreement with people not yet measured.",
    measured: (kappa: number | null, raw: number, answers: number, model: string) =>
      `Agreed with people on ${Math.round(raw * 100)}% of ${answers} answers${kappa === null ? "" : ` (kappa ${kappa.toFixed(2)})`}, judged by ${model}.`,
    needsJudge: "Judges need a model to read the answers. You choose it when you score on the Results step.",
  },
  rules: {
    intro:
      "A rule is a fixed check done by a program: free, instant and the same every time. It only looks at the answer text.",
    search: "Find a rule",
    searchPlaceholder: "For example length, JSON, tool",
    empty: "No rule matches that.",
    noSettings: "This rule has nothing to set.",
    settings: "Settings",
    passMark: "Pass mark",
    passMarkHint:
      "A rule gives a score from 0 to 100%. It passes at this value or above. 100% means the answer must be fully right.",
    lines: "One per line",
    optional: "optional",
    pick: "Choose a rule",
    unavailable: "This server did not list any rules.",
  },
  code: {
    intro:
      "Write a short Python function named check. It gets one case and returns a score from 0 to 1 (or true or false), with a reason if you like. It runs in a locked box with no internet and no files.",
    name: "Name of the check",
    namePlaceholder: "For example short answer",
    editor: "Your check",
    editorHint: "Python only. Names that start with an underscore are not allowed.",
    returns:
      'Return a number from 0 to 1, true or false, a pair like (0.8, "reason"), or a dictionary with score, passed and reason.',
    allowed:
      "You can import: re, json, math, statistics, string, itertools, functools, collections, datetime, decimal, fractions, difflib, unicodedata, textwrap, typing, dataclasses, html, urllib.parse, base64 and hashlib.",
    limits: (wall: number, memory: number, output: number) =>
      `Each run may take up to ${wall} seconds and ${memory} MB of memory, and its reply is cut at ${output} characters.`,
    off: "Custom code checks are switched off on this server.",
    tryHeading: "Try it on a sample answer",
    sampleOutput: "Sample answer",
    sampleExpected: "Expected answer (optional)",
    sampleInput: "Sample input (optional)",
    tryButton: "Run the check",
    trying: "Running…",
    result: "Result",
    score: "Score",
    reason: "Reason",
    errorTitle: "The check did not run",
    timedOut: "It took too long and was stopped. Make it simpler.",
    needTitle: "Give the check a name.",
    needCode: "Write the check first.",
    needTry: "Run it once on a sample before adding it, so you know it works.",
    passMark: "Pass mark",
  },
}
