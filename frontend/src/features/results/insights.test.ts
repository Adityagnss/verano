import { describe, expect, it } from "vitest"

import type { ModelMetricsOut } from "@/lib/api/types"

import { bestValue, verdict } from "./insights"

const model = (id: string, extra: Partial<ModelMetricsOut> = {}) =>
  ({
    model_profile_id: id,
    model: id,
    quality: 0.8,
    cost_per_call: 0.01,
    latency_ms: 100,
    cases: 10,
    failed_calls: 0,
    vs_best: null,
    ...extra,
  }) as unknown as ModelMetricsOut

describe("verdict", () => {
  it("says unfair when the runs differ", () => {
    expect(verdict([model("a")], false).kind).toBe("unfair")
  })
  it("is clear when every other model is clearly worse", () => {
    const v = verdict(
      [
        model("a", { quality: 0.9 }),
        model("b", { quality: 0.5, vs_best: { label: "clear difference" } as never }),
      ],
      true,
    )
    expect(v.kind).toBe("clear")
  })
  it("is close when the gap could be chance", () => {
    const v = verdict(
      [
        model("a", { quality: 0.9 }),
        model("b", { quality: 0.85, vs_best: { label: "no clear difference" } as never }),
      ],
      true,
    )
    expect(v.kind).toBe("close")
  })
  it("is single with one model", () => {
    expect(verdict([model("a")], true).kind).toBe("single")
  })
})

describe("bestValue", () => {
  it("picks the most quality per dollar", () => {
    const best = bestValue([
      model("pricey", { quality: 0.9, cost_per_call: "0.10" as never }),
      model("cheap", { quality: 0.8, cost_per_call: "0.01" as never }),
    ])
    expect(best?.model).toBe("cheap")
  })
  it("is null without costs", () => {
    expect(bestValue([model("a", { cost_per_call: null })])).toBeNull()
  })
})
