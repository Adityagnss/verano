import { describe, expect, it } from "vitest"

import { diffCounts, lineDiff, promptText } from "./diff"

describe("what changed between two prompts", () => {
  it("lists added and removed lines and counts them", () => {
    const lines = lineDiff(
      "Be brief.\nNever offer discounts.\nSign off warmly.",
      "Be brief.\nNever offer discounts or promo codes.\nSign off warmly.\nAsk one question.",
    )
    expect(lines.filter((l) => l.kind !== "same").map((l) => `${l.kind}: ${l.text}`)).toEqual([
      "remove: Never offer discounts.",
      "add: Never offer discounts or promo codes.",
      "add: Ask one question.",
    ])
    expect(diffCounts(lines)).toEqual({ added: 2, removed: 1 })
    expect(diffCounts(lineDiff("same", "same"))).toEqual({ added: 0, removed: 0 })
  })

  it("reads a prompt as its system part then its user part", () => {
    expect(promptText({ system_template: "A", user_template: "B" })).toBe("[system]\nA\n[user]\nB")
  })
})
