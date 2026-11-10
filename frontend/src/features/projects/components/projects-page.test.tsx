import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

const push = vi.fn()
const mutateAsync = vi.fn(async (name: string) => ({ id: "p1", name }))
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), usePathname: () => "/projects" }))
vi.mock("./account-frame", () => ({
  AccountFrame: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
vi.mock("../hooks", () => ({
  useProjects: () => ({ data: { items: [] }, isSuccess: true, error: null }),
  useCreateProject: () => ({ mutateAsync, isPending: false, error: null }),
  useStepCompletion: () => ({ data: undefined }),
  useCostSummary: () => ({ data: undefined }),
}))
vi.mock("@/features/run/hooks", () => ({ useExperiments: () => ({ data: [] }) }))

import { freeDefaultName, ProjectsPage } from "./projects-page"

describe("ProjectsPage first visit", () => {
  it("offers three starting paths and opens the app path", async () => {
    render(<ProjectsPage />)
    expect(screen.getByRole("button", { name: /Compare models on a prompt/ })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Bring prompts from my code/ })).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: /Test an app I already run/ }))
    expect(push).toHaveBeenCalledWith("/projects/p1/apps")
  })
  it("shows the three commands for the code path", async () => {
    render(<ProjectsPage />)
    await userEvent.click(screen.getByRole("button", { name: /Bring prompts from my code/ }))
    expect(await screen.findByText("verano login")).toBeInTheDocument()
    expect(screen.getByText("verano init")).toBeInTheDocument()
    expect(screen.getByText("verano push")).toBeInTheDocument()
  })
})

describe("freeDefaultName", () => {
  it("uses the friendly name first, then numbers, never one already taken", () => {
    expect(freeDefaultName([])).toBe("My first project")
    expect(freeDefaultName(["my first project "])).toBe("My project 2")
    expect(freeDefaultName(["My first project", "My project 2"])).toBe("My project 3")
  })
})
