import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { GUIDE_SECTIONS } from "../sections"
import { GuideSectionPage } from "./guide-section-page"
import { GuidePage } from "./guide-page"

vi.mock("../hooks", () => ({
  usePromptNotes: () => ({
    data: "# Prompting guide\n\n## Start here\nHello\n\n## The one habit: measure first\nMeasure.",
    error: null,
    isPending: false,
  }),
}))

describe("guide pages", () => {
  it("lists every section as a link on the index", () => {
    render(<GuidePage projectId="p1" />)
    for (const section of GUIDE_SECTIONS)
      expect(screen.getAllByRole("link", { name: new RegExp(section.title) }).length).toBeGreaterThan(0)
  })

  it("shows a section with a next link and no previous link on the first page", () => {
    render(<GuideSectionPage projectId="p1" section="start-here" />)
    expect(screen.getByRole("heading", { name: "Start here", level: 1 })).toBeInTheDocument()
    expect(screen.getByText("Measure.")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /^Next:/ })).toHaveAttribute(
      "href",
      "/projects/p1/guide/parts-of-a-prompt",
    )
    expect(screen.queryByRole("link", { name: /^Previous:/ })).toBeNull()
  })

  it("says so for an unknown section", () => {
    render(<GuideSectionPage projectId="p1" section="nope" />)
    expect(screen.getByText("This guide page does not exist")).toBeInTheDocument()
  })
})
