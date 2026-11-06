/** User-facing text for prompt labels. */
export const LABELS_COPY = {
  title: "Where your app gets this prompt",
  description:
    "A label such as production points at one saved version. Your app asks for the label, so you can change what it gets without changing its code.",
  empty: "No labels yet. Point production at a version to start serving it to your app.",
  name: "Label",
  version: "Version",
  moved: (when: string) => `moved ${when}`,
  set: "Set label",
  customPlaceholder: "or a name of your own",
  setDone: (name: string, version: number) => `${name} now points at version ${version}.`,
  rollBack: "Roll back",
  rolledBack: (name: string, version: number) => `${name} is back on version ${version}.`,
  cannotRollBack: "It has only ever pointed at this version.",
  remove: "Remove",
  removed: (name: string) => `${name} removed. Apps asking for it will get an error.`,
  acceptHeading: "When I accept an improvement",
  acceptOff: "Don't move any label (my choice each time)",
  acceptOn: (name: string) => `Move ${name} to the accepted version`,
  acceptHelp:
    "Off by default. When on, accepting an improvement also changes what your app gets. You can roll it back here in one click.",
  acceptSaved: "Saved.",
  historyHeading: "History",
  historyEmpty: "Nothing has moved yet.",
  reasons: {
    assign: "set by hand",
    accept: "accepted improvement",
    rollback: "rolled back",
    remove: "removed",
  } as Record<string, string>,
  historyLine: (from: number | null, to: number | null) =>
    from === null ? `to version ${to}` : to === null ? `was version ${from}` : `version ${from} to ${to}`,
  by: (name: string | null) => (name ? `by ${name}` : ""),
  suggested: ["production", "staging"],
}
