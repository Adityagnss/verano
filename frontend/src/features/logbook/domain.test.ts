import { describe, expect, it } from "vitest"

import type { AnalysisOut, GroupStats } from "@/lib/api/types"
import { compareVersions, versionName } from "@/lib/format"

import { findings, grid, trendVersions } from "./domain"

const group = (prompt_version: number, pass_rate: number): GroupStats =>
  ({
    prompt_version,
    model: "m",
    pass_rate,
    answers: 4,
    cost: null,
    failed_calls: 0,
  }) as unknown as GroupStats

describe("prompt versions in the logbook", () => {
  it("orders saved versions oldest to newest, then Improve's candidates in the order written", () => {
    expect([-9, -1, 2, 1].sort(compareVersions)).toEqual([1, 2, -1, -9])
    expect(versionName(-6)).toBe("Candidate 6")
    expect(versionName(3)).toBe("v3")
  })

  it("draws the trend over saved versions only, oldest first", () => {
    const groups = [group(-9, 0.9), group(2, 0.6), group(1, 0.5), group(-1, 0.8)]
    expect(trendVersions(groups)).toEqual([1, 2])
    expect(grid(groups).versions).toEqual([1, 2, -1, -9])
  })

  it("describes a change between versions without calling it an improvement", () => {
    const analysis = {
      totals: { answers: 8, unknown_price_answers: 0 },
      groups: [group(1, 0.5), group(2, 0.9)],
      failed_checks: [],
    } as unknown as AnalysisOut
    const text = findings(analysis).join(" ")
    expect(text).toContain("50% on v1, 90% on v2")
    expect(text).not.toMatch(/went from|points/)
  })
})
