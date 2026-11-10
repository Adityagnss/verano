import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { CommandPalette } from "./command-palette"

const push = vi.fn()
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/projects/p1/results",
}))
vi.mock("@/features/projects/hooks", () => ({
  useProjects: () => ({ data: { items: [{ id: "p2", name: "Support triage" }] } }),
}))

describe("CommandPalette", () => {
  it("opens with Ctrl+K and lists pages and projects", async () => {
    const user = userEvent.setup()
    render(<CommandPalette />)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    await user.keyboard("{Control>}k{/Control}")
    expect(await screen.findByRole("dialog")).toBeInTheDocument()
    expect(screen.getByText("Compare results")).toBeInTheDocument()
    expect(screen.getByText("Usage and spend")).toBeInTheDocument()
    expect(screen.getByText("Support triage")).toBeInTheDocument()
    await user.click(screen.getByText("Support triage"))
    expect(push).toHaveBeenCalledWith("/projects/p2/keys")
  })
})
