/** Pure helpers for projects with several prompts: which prompts the experiments used, and filtering by one. */
type Tagged = { prompt_id?: string | null; prompt_name?: string | null }

/** The distinct prompts the experiments were run on, in the order first seen. */
export function promptsOf(experiments: Tagged[]): { id: string; name: string }[] {
  const seen = new Map<string, string>()
  for (const e of experiments) {
    if (e.prompt_id && !seen.has(e.prompt_id)) seen.set(e.prompt_id, e.prompt_name ?? "Prompt")
  }
  return [...seen].map(([id, name]) => ({ id, name }))
}

/** Only the experiments of one prompt. With no prompt chosen, or experiments that do not name theirs, all stay. */
export function forPrompt<T extends Tagged>(experiments: T[], promptId: string | null): T[] {
  if (!promptId) return experiments
  return experiments.filter((e) => e.prompt_id === promptId)
}

/** "Refund bot · " in front of an experiment's name, but only when the project has more than one prompt. */
export function promptTag(experiment: Tagged, all: Tagged[]): string {
  if (promptsOf(all).length < 2 || !experiment.prompt_name) return ""
  return `${experiment.prompt_name} · `
}

/** The prompt to show first: the one the newest experiment used, else the first one. */
export function defaultPrompt(experiments: Tagged[]): string | null {
  return experiments.find((e) => e.prompt_id)?.prompt_id ?? null
}
