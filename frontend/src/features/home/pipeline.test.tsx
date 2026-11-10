import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { setViewport } from "@/test/viewport"

import { EMPTY_COMPLETION, nodeStates } from "./home-logic"
import { Pipeline } from "./pipeline"

describe("Pipeline", () => {
  it("links every node to its page with its state in the name", () => {
    setViewport(390)
    render(<Pipeline base="/projects/p1" states={nodeStates({ ...EMPTY_COMPLETION, keys: true })} />)
    expect(screen.getByRole("link", { name: "Keys: Done" })).toHaveAttribute("href", "/projects/p1/keys")
    expect(screen.getByRole("link", { name: "Prompt: Up next" })).toHaveAttribute(
      "href",
      "/projects/p1/prompt",
    )
    expect(screen.getByRole("link", { name: "Improve: To do" })).toBeInTheDocument()
  })
})
