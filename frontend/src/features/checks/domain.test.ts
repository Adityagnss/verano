import { describe, expect, it } from "vitest"

import { buildRuleConfig, codeCheckName, parseSettings } from "./domain"

describe("rule settings", () => {
  it("reads the settings text of a rule", () => {
    const fields = parseSettings("values (list), case_sensitive (default false)")
    expect(fields.map((f) => [f.name, f.kind, f.required])).toEqual([
      ["values", "lines", true],
      ["case_sensitive", "bool", false],
    ])
    expect(parseSettings("none")).toEqual([])
  })

  it("names every problem and keeps list values one per line", () => {
    const fields = parseSettings("values (list), case_sensitive (default false)")
    expect(buildRuleConfig(fields, {}).errors).toHaveLength(1)
    const ok = buildRuleConfig(fields, { values: "a\n b \n", case_sensitive: true })
    expect(ok.errors).toEqual([])
    expect(ok.config).toEqual({ kind: "rule", values: ["a", "b"], case_sensitive: true })
  })
})

describe("code check names", () => {
  it("never repeats a taken name", () => {
    expect(codeCheckName("Short answer!", ["code_short_answer"])).toBe("code_short_answer_2")
  })
})
