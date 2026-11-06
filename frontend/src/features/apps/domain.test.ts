import { describe, expect, it } from "vitest"

import { parseInputs } from "./domain"

describe("parseInputs", () => {
  it("reads name=value lines and keeps an equals sign inside a value", () => {
    expect(parseInputs("question=How long?\nq2=a=b")).toEqual({ question: "How long?", q2: "a=b" })
  })

  it("ignores lines that have no name or no equals sign", () => {
    expect(parseInputs("just text\n=nothing\n\nok=1")).toEqual({ ok: "1" })
  })
})
