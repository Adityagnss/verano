import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { Checklist } from "./checklist"

const none = { connected: false, hasTraffic: false, caseMade: false, hasAlertRule: false }

describe("Checklist", () => {
  it("shows four steps and marks the first as current", () => {
    render(<Checklist state={none} />)
    expect(screen.getAllByRole("listitem")).toHaveLength(4)
    expect(screen.getAllByRole("listitem")[0]).toHaveAttribute("aria-current", "step")
  })
  it("marks finished steps in words and moves the current step", () => {
    render(<Checklist state={{ ...none, connected: true }} />)
    expect(screen.getByText("(done)")).toBeInTheDocument()
    expect(screen.getAllByRole("listitem")[1]).toHaveAttribute("aria-current", "step")
  })
  it("opens a step", async () => {
    const onOpen = vi.fn()
    render(<Checklist state={none} onOpen={onOpen} />)
    await userEvent.click(screen.getAllByRole("button", { name: "Go to this step" })[0])
    expect(onOpen).toHaveBeenCalledWith("connected")
  })
})
