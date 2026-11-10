import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import { PageIntro } from "./page-intro"

const props = {
  storageKey: "test-page",
  title: "Compare results",
  what: "Quality, cost and speed side by side.",
  whenToUse: "a run has finished",
  youGet: "a ranking",
  learnMore: "results",
}

describe("PageIntro", () => {
  it("shows the full intro on an empty page, with one h1 and a learn more link", () => {
    render(<PageIntro {...props} primaryAction={<button>Run the test</button>} />)
    expect(screen.getByRole("heading", { level: 1, name: "Compare results" })).toBeInTheDocument()
    expect(screen.getByText("a run has finished")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /learn more/i })).toHaveAttribute(
      "href",
      "https://docs.verano.example/results",
    )
    expect(screen.getByRole("button", { name: "Run the test" })).toBeInTheDocument()
  })

  it("starts collapsed when the page has content", () => {
    render(<PageIntro {...props} hasContent />)
    expect(screen.getByTestId("page-intro")).toHaveAttribute("data-expanded", "false")
    expect(screen.queryByText("a ranking")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: /show help/i })).toBeInTheDocument()
  })

  it("remembers a dismissal", async () => {
    const user = userEvent.setup()
    const { unmount } = render(<PageIntro {...props} />)
    await user.click(screen.getByRole("button", { name: /hide help/i }))
    expect(window.localStorage.getItem("verano.intro.test-page")).toBe("1")
    unmount()
    render(<PageIntro {...props} />)
    expect(screen.getByTestId("page-intro")).toHaveAttribute("data-expanded", "false")
  })
})
