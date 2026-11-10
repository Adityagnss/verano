import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { VerdictCard, verdictKind } from "./verdict-card"

describe("verdict card", () => {
  it("maps reasons to three plain words", () => {
    expect(verdictKind("proven")).toBe("better")
    expect(verdictKind("worse")).toBe("worse")
    expect(verdictKind("too_few_cases")).toBe("not_proven")
  })

  it("shows the word and the held-back numbers", () => {
    render(<VerdictCard reason="proven" before={0.5} after={0.8} />)
    expect(screen.getByText("Proven better")).toBeInTheDocument()
    expect(screen.getByText(/50% before, 80% now/)).toBeInTheDocument()
  })

  it("says Not proven when the numbers are missing", () => {
    render(<VerdictCard reason="not_proven" before={null} after={undefined} />)
    expect(screen.getByText("Not proven")).toBeInTheDocument()
    expect(screen.getByText(/n\/a before, n\/a now/)).toBeInTheDocument()
  })
})
