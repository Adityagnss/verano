/** Text for the blind review switch, the "clearly better" and "proven" explanation, and recorded app calls. */
export const BLIND_COPY = {
  label: "Blind review",
  explain:
    "Blind review hides the judge's pass or fail and its scores, so you can label each answer on its own merits without being swayed. Your labels are still saved. Turn it off to see the scores again.",
  hidden: "Judge's verdict hidden",
}

export const PROOF_COPY = {
  heading: "What “clearly better” and “proven” mean",
  clearly: (n: number) =>
    `Clearly better: two prompts or models were compared on at least ${n} test cases that both were judged on, and the gap is larger than chance would explain. With fewer cases the result says “too few cases to tell”.`,
  proven: (n: number) =>
    `Proven: an improvement is only called proven when it also wins on at least ${n} held-back test cases, which Improve never looked at while it was writing the new prompt. A win on cases it practised on is not proof.`,
  difference:
    "So “clearly better” is a statement about one comparison, and “proven” asks for fresh cases as well. A prompt can be clearly better without being proven yet.",
  fallback: "Loading the exact numbers…",
}

export const CALLS_COPY = {
  heading: "What was sent to your app",
  open: "Show the app's recorded calls",
  close: "Hide the calls",
  loading: "Loading the recorded calls…",
  none: "No call to your app was recorded for this answer.",
  turn: (n: number) => `Turn ${n}`,
  sent: "Sent",
  received: "Reply",
  status: (code: number | null) => (code === null ? "No reply" : `Status ${code}`),
  latency: (ms: number | null) => (ms === null ? "time unknown" : `${ms} ms`),
  truncated: "The reply was longer than the storage limit and was cut.",
  failed: "The call failed",
}
