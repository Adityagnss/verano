import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { AgreementMeter, pickCard, shortcutFor } from "./review-step"

describe("review helpers", () => {
  it("maps the shortcut keys", () => {
    expect(shortcutFor("g")).toBe("good")
    expect(shortcutFor("B")).toBe("bad")
    expect(shortcutFor("u")).toBe("unsure")
    expect(shortcutFor("ArrowRight")).toBe("next")
    expect(shortcutFor("x")).toBeNull()
  })
  it("wraps the card position both ways", () => {
    expect(pickCard(["a", "b", "c"], 4)).toEqual({ item: "b", index: 1 })
    expect(pickCard(["a", "b", "c"], -1)).toEqual({ item: "c", index: 2 })
    expect(pickCard([], 3).item).toBeNull()
  })
})

describe("AgreementMeter", () => {
  it("asks for more labels when there are too few", () => {
    render(<AgreementMeter raw={null} warn={false} tooFew labelled={10} minLabels={30} />)
    expect(screen.getByText(/Label 20 more answers/)).toBeInTheDocument()
  })
  it("warns when the judge disagrees too often", () => {
    render(<AgreementMeter raw={0.5} warn tooFew={false} labelled={30} minLabels={30} />)
    expect(screen.getByRole("progressbar", { name: "Agreement with the judge" })).toHaveAttribute(
      "aria-valuenow",
      "50",
    )
    expect(screen.getByText(/disagrees with you too often/)).toBeInTheDocument()
  })
})
