import { describe, expect, it } from "vitest"

import type { VersionComparisonOut } from "@/lib/api/types"

import { type Finished, insights, yourRuns } from "./domain"

function run(label: string, origin: "manual" | "optimization", passRate: number): Finished {
  return {
    label,
    experiment: { origin } as Finished["experiment"],
    results: {
      models: [{ model: "m", pass_rate: passRate, unscored_cases: 0, failed_calls: 0, consistency: null }],
    } as unknown as Finished["results"],
  }
}

/** What the compare endpoint says for one model (the dashboard test has a single model, "m"). */
const compare = (label: string, firstBetter: boolean | null) =>
  ({ models: [{ model: "m", comparison: { label, first_better: firstBetter } }] }) as VersionComparisonOut

describe("dashboard findings", () => {
  const runs = [run("v1", "manual", 0.5), run("v2", "manual", 0.8)]

  it("keeps Improve's candidate tests out of your numbers", () => {
    const all = [run("v1", "manual", 0.5), run("v?", "optimization", 0.8)]
    expect(yourRuns(all).map((f) => f.label)).toEqual(["v1"])
  })

  it("calls a change an improvement only when the comparison finds a clear difference", () => {
    const notes = insights(runs, undefined, compare("clear difference", true))
    expect(notes).toContain("m: v2 is clearly better than v1 (pass rate 50% to 80%).")
  })

  it("says a change is not proven, and gives no points, when the difference is not clear", () => {
    const text = insights(runs, undefined, compare("too few cases", null)).join(" ")
    expect(text).toContain("not a proven difference (too few test cases)")
    expect(text).not.toContain("points")
  })

  it("says nothing about a change until the comparison has loaded", () => {
    expect(insights(runs, undefined, null).join(" ")).not.toMatch(/v1.*v2|v2.*v1/)
  })
})
