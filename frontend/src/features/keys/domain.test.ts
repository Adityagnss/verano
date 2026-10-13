import { describe, expect, it } from "vitest"

import type { ModelProfileOut } from "@/lib/api/types"

import { isNoiseModel, suggestModels } from "./domain"

const model = (name: string, price: number): ModelProfileOut =>
  ({
    id: name,
    model_name: name,
    display_name: name,
    price_known: true,
    price_source: "provider",
    input_price_per_mtok: String(price),
    output_price_per_mtok: String(price),
    context_window: 128_000,
  }) as ModelProfileOut

describe("choosing models", () => {
  it("hides dated copies and models that are not for answering prompts", () => {
    for (const name of [
      "gpt-4o-2024-08-06",
      "text-embedding-3-small",
      "gpt-4o-mini-tts",
      "gpt-5-chat-latest",
    ])
      expect(isNoiseModel({ model_name: name }), name).toBe(true)
    for (const name of ["gpt-4.1-nano", "gpt-5.6-luna", "claude-sonnet-5-5"])
      expect(isNoiseModel({ model_name: name }), name).toBe(false)
  })

  it("suggests a cheap, a middle and a strong model from what the keys reach", () => {
    const models = ["a", "b", "c", "d", "e", "f", "g"].map((n, i) => model(`model-${n}`, (i + 1) * 10))
    models.push(model("model-dated-2024-08-06", 1), { ...model("model-unpriced", 0), price_known: false })
    const picked = suggestModels(models).map((s) => `${s.tier}:${s.model.model_name}`)
    // spread over the price range (about the 15th, 50th and 85th percentile), not the very cheapest or dearest
    expect(picked).toEqual(["cheap:model-b", "balanced:model-d", "strong:model-f"])
  })
})
