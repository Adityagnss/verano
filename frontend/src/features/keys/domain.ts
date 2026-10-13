/** Pure rules for choosing models: which ones are noise, and three that suit most tests. No React here. */
import type { ModelProfileOut } from "@/lib/api/types"

// A dated copy of a model (gpt-4o-2024-08-06), or a model that is not a chat model for answering prompts.
const SNAPSHOT = /-(?:20\d{2}[-_]?\d{2}[-_]?\d{2}|\d{4}|\d{2}-\d{2})$/
const NOT_FOR_PROMPTS =
  /(embed|tts|whisper|transcribe|audio|image|dall-e|moderation|realtime|search|computer-use|instruct|chat-latest|davinci|babbage)/i

export function isNoiseModel(model: Pick<ModelProfileOut, "model_name">): boolean {
  return SNAPSHOT.test(model.model_name) || NOT_FOR_PROMPTS.test(model.model_name)
}

const price = (m: ModelProfileOut) => Number(m.input_price_per_mtok) + Number(m.output_price_per_mtok)

export type Tier = "cheap" | "balanced" | "strong"
export type Suggestion = { tier: Tier; model: ModelProfileOut }

/** Up to three models spread over the price range of what the key reaches: a cheap one, a middle one and a strong
 * one. Models with an unknown price, noise models and very small context windows are left out. */
export function suggestModels(models: ModelProfileOut[]): Suggestion[] {
  const pool = models
    .filter((m) => m.price_known && !isNoiseModel(m) && (m.context_window ?? 0) >= 16_000)
    .sort((a, b) => price(a) - price(b) || a.display_name.localeCompare(b.display_name))
  if (pool.length === 0) return []
  const at = (share: number) => pool[Math.min(pool.length - 1, Math.round((pool.length - 1) * share))]
  const picks: Suggestion[] = [
    { tier: "cheap", model: at(0.15) },
    { tier: "balanced", model: at(0.5) },
    { tier: "strong", model: at(0.85) },
  ]
  const seen = new Set<string>()
  return picks.filter((p) => !seen.has(p.model.id) && seen.add(p.model.id))
}
