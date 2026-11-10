import { describe, expect, it } from "vitest"

import { pct, rateLevel, reviewBlocker, reviewSummary } from "./domain"

const cases = [
  { category: "a", status: "approved" },
  { category: "a", status: "draft" },
  { category: "b", status: "draft" },
]

describe("review helpers", () => {
  it("counts only the chosen kinds and lists the rest to drop", () => {
    const s = reviewSummary(cases, new Set(["a"]))
    expect(s.pending).toBe(1)
    expect(s.approved).toBe(1)
    expect(s.toDrop).toHaveLength(1)
  })

  it("blocks until every chosen case is decided", () => {
    expect(reviewBlocker(cases, new Set(["a"]))).toMatch(/1 attack still needs/)
    expect(reviewBlocker([{ category: "a", status: "approved" }], new Set(["a"]))).toBe(true)
    expect(reviewBlocker([{ category: "a", status: "rejected" }], new Set(["a"]))).toMatch(/at least one/)
  })
})

describe("report helpers", () => {
  it("formats rates and names the level in words", () => {
    expect(pct(0.756)).toBe("76%")
    expect(pct(null)).toBe("n/a")
    expect(rateLevel(0.9).word).toBe("Holds")
    expect(rateLevel(0.6).word).toBe("Weak")
    expect(rateLevel(0.1).word).toBe("Fails")
  })
})
