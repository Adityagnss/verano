import { describe, expect, it } from "vitest"

import {
  ACCOUNT_NAV,
  ALL_PROJECT_PAGES,
  docsUrl,
  learnMoreForPath,
  NAV_GROUPS,
  pageTitleForPath,
  PROJECT_NAV,
  projectHref,
} from "./nav"
import { STEPS } from "./steps"

describe("nav", () => {
  it("uses the new page names", () => {
    expect(pageTitleForPath("/projects/p1/keys")).toBe("Connect models")
    expect(pageTitleForPath("/projects/p1/data")).toBe("Add examples")
    expect(pageTitleForPath("/projects/p1/dashboard")).toBe("Trends")
    expect(pageTitleForPath("/activity")).toBe("Usage and spend")
    expect(pageTitleForPath("/projects")).toBe("Projects")
    expect(pageTitleForPath("/nowhere")).toBeUndefined()
  })

  it("keeps every route segment unique and every group used", () => {
    const segments = ALL_PROJECT_PAGES.map((page) => page.segment)
    expect(new Set(segments).size).toBe(segments.length)
    for (const group of NAV_GROUPS) {
      expect(PROJECT_NAV.some((page) => page.group === group.id)).toBe(true)
    }
    expect(segments).toEqual(
      expect.arrayContaining(["keys", "prompt", "data", "tests", "run", "results", "improve", "security"]),
    )
  })

  it("builds hrefs and docs links", () => {
    expect(projectHref("abc", "run")).toBe("/projects/abc/run")
    expect(docsUrl("results")).toBe("https://docs.verano.example/results")
    expect(learnMoreForPath("/tokens")).toBe("api-tokens")
    expect(ACCOUNT_NAV.map((page) => page.href)).toEqual(["/activity", "/workspace", "/tokens"])
  })

  it("derives the guided steps from the navigation", () => {
    expect(STEPS.map((step) => step.key)).toEqual([
      "keys",
      "prompt",
      "data",
      "tests",
      "run",
      "results",
      "improve",
    ])
    expect(STEPS[0].label).toBe("Connect models")
  })
})
