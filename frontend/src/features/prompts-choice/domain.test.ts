import { describe, expect, it } from "vitest"

import { forPrompt, promptTag, promptsOf } from "./domain"

const runs = [
  { prompt_id: "a", prompt_name: "Refunds" },
  { prompt_id: "b", prompt_name: "Greeting" },
  { prompt_id: "a", prompt_name: "Refunds" },
]

describe("several prompts in one project", () => {
  it("lists each prompt once and filters by it", () => {
    expect(promptsOf(runs)).toEqual([
      { id: "a", name: "Refunds" },
      { id: "b", name: "Greeting" },
    ])
    expect(forPrompt(runs, "a")).toHaveLength(2)
    expect(forPrompt(runs, null)).toHaveLength(3)
  })

  it("names the prompt only when there is more than one", () => {
    expect(promptTag(runs[0], runs)).toBe("Refunds · ")
    expect(promptTag(runs[0], [runs[0]])).toBe("")
  })
})
