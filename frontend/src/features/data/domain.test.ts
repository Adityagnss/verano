import { describe, expect, it } from "vitest"

import { inputPurpose } from "./domain"

describe("how an input file is read", () => {
  it("makes every row of a table its own test case, unless the whole file is one input", () => {
    for (const name of ["messages.csv", "Messages.XLSX", "a.jsonl", "b.json", "c.tsv"])
      expect(inputPurpose(name, false)).toBe("input_rows")
    expect(inputPurpose("messages.csv", true)).toBe("input")
  })

  it("always reads a text or Markdown file as one input", () => {
    expect(inputPurpose("policy.txt", false)).toBe("input")
    expect(inputPurpose("notes.md", false)).toBe("input")
  })
})
