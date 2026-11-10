import { describe, expect, it } from "vitest"

import { EMPTY_COMPLETION, nextStep, nodeStates } from "./home-logic"

describe("home logic", () => {
  it("marks the first unfinished node as current", () => {
    const s = nodeStates({ ...EMPTY_COMPLETION, keys: true, prompt: true })
    expect(s.keys).toBe("done")
    expect(s.tests).toBe("current")
    expect(s.run).toBe("todo")
  })
  it("picks the next step and ends with null", () => {
    expect(nextStep(EMPTY_COMPLETION)?.segment).toBe("keys")
    expect(nextStep({ ...EMPTY_COMPLETION, keys: true })?.segment).toBe("prompt")
    const all = { keys: true, prompt: true, data: true, tests: true, run: true, results: true, improve: true }
    expect(nextStep(all)).toBeNull()
  })
})
