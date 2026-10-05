/**
 * Run configuration helpers shared by Run, Results and the Logbook: the short form of a
 * configuration hash, which experiments were set up the same way, how settings read, and
 * the three layers of configuration (what you set, what Verano locks, what the provider controls).
 */

export const shortHash = (hash: string) => hash.slice(0, 8)

/** The other experiments with the same configuration hash. Replicable, not necessarily stable. */
export function sameConfiguration<T extends { id: string }>(
  experiments: T[],
  id: string,
  hashOf: (experiment: T) => string,
): T[] {
  const current = experiments.find((e) => e.id === id)
  if (!current) return []
  const hash = hashOf(current)
  return experiments.filter((e) => e.id !== id && hashOf(e) === hash)
}

/** "temperature 0 · seed 42 · 2 stop sequences" */
export function formatParams(params: Record<string, unknown>): string {
  const parts = Object.entries(params).map(([name, value]) => {
    if (name === "stop" && Array.isArray(value))
      return `${value.length} stop sequence${value.length === 1 ? "" : "s"}`
    return `${name.replaceAll("_", " ")} ${String(value)}`
  })
  return parts.length ? parts.join(" · ") : "provider defaults"
}

export const CONFIG_LAYERS = {
  youSet: {
    title: "You set",
    text: "Model, prompt, test cases, sampling settings, runs and the checks that score the answers.",
  },
  locked: {
    title: "Verano locks and records",
    text: "Exact versions, a fingerprint of the configuration, the run id, library versions, and for every call its cost, tokens, time and retries.",
  },
  provider: {
    title: "The provider controls",
    text: "The model snapshot behind a name, hardware, routing and safety systems. Verano records what the provider reports, but cannot guarantee it stays the same.",
  },
  wording:
    "Same configuration means the experiments were set up identically, so you can run it again. It does not promise identical answers: a fixed seed helps, but providers can change models, hardware or routing.",
} as const
