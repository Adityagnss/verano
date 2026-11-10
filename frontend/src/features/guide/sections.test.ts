import { describe, expect, it } from "vitest"

import { GUIDE_SECTIONS, findSection, neighbours, sectionMarkdown, splitByHeading } from "./sections"

const SOURCE = [
  "# Prompting guide",
  "intro",
  "## Start here",
  "a",
  "```",
  "## not a heading",
  "```",
  "## Checklist for a new prompt version",
  "c",
  "## Brand new topic",
  "n",
].join("\n")

describe("guide sections", () => {
  it("splits at level-2 headings and ignores code fences", () => {
    expect(splitByHeading(SOURCE).map((p) => p.title)).toEqual([
      "Start here",
      "Checklist for a new prompt version",
      "Brand new topic",
    ])
  })
  it("gives each page its headings and sends unknown ones to the last page", () => {
    expect(sectionMarkdown(SOURCE, GUIDE_SECTIONS[0])).toContain("## not a heading")
    const last = sectionMarkdown(SOURCE, GUIDE_SECTIONS[GUIDE_SECTIONS.length - 1])
    expect(last).toContain("## Brand new topic")
    expect(last).not.toContain("## Start here")
  })
  it("links previous and next", () => {
    expect(neighbours(GUIDE_SECTIONS[0]).previous).toBeUndefined()
    expect(neighbours(findSection("cheat-sheet")!).next?.slug).toBe("techniques")
  })
})
