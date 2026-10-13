import { describe, expect, it } from "vitest"

import { unfairReasons } from "./fairness"

const experiment = (models: { display_name: string; runs: number; params: Record<string, unknown> }[]) =>
  ({ config: { models } }) as Parameters<typeof unfairReasons>[0]

describe("a fair comparison between models", () => {
  it("is fair when every model ran the same number of times with the same settings", () => {
    const same = { runs: 3, params: { temperature: 0 } }
    expect(
      unfairReasons(
        experiment([
          { display_name: "a", ...same },
          { display_name: "b", ...same },
        ]),
      ),
    ).toEqual([])
    expect(unfairReasons(experiment([{ display_name: "a", ...same }]))).toEqual([])
  })

  it("names the models whose runs or settings differ", () => {
    const reasons = unfairReasons(
      experiment([
        { display_name: "gpt-4o-mini", runs: 1, params: { temperature: 0 } },
        { display_name: "gpt-4.1-nano", runs: 5, params: {} },
      ]),
    )
    expect(reasons).toEqual([
      "The models answered each case a different number of times (gpt-4o-mini: 1, gpt-4.1-nano: 5).",
      "The models ran with different settings (gpt-4o-mini: temperature 0; gpt-4.1-nano: its own defaults).",
    ])
  })
})
