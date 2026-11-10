import { act, render, renderHook, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { setViewport } from "@/test/viewport"

import { AnimatedNumber } from "./animated-number"
import { EmptyState } from "./empty-state"
import { MotionProvider } from "./motion-provider"
import { ResponsiveTable } from "./responsive-table"
import { breakpointForWidth, useBreakpoint } from "./use-breakpoint"

const rows = [
  { id: "1", name: "gpt-small", cost: "$0.10" },
  { id: "2", name: "claude-mini", cost: "$0.20" },
]
const columns = [
  { id: "name", header: "Model", primary: true, cell: (r: (typeof rows)[number]) => r.name },
  { id: "cost", header: "Cost", cell: (r: (typeof rows)[number]) => r.cost },
]

describe("useBreakpoint", () => {
  it("maps widths to Tailwind bands", () => {
    expect(breakpointForWidth(390)).toBe("base")
    expect(breakpointForWidth(768)).toBe("md")
    expect(breakpointForWidth(1279)).toBe("lg")
    expect(breakpointForWidth(1440)).toBe("xl")
  })

  it("follows the window", () => {
    setViewport(1100)
    const { result } = renderHook(() => useBreakpoint())
    expect(result.current.atLeast("lg")).toBe(true)
    expect(result.current.atLeast("xl")).toBe(false)
    act(() => {
      setViewport(500)
      window.dispatchEvent(new Event("resize"))
    })
    expect(result.current.current).toBe("base")
  })
})

describe("ResponsiveTable", () => {
  it("is a table at 768px and a list of cards below", () => {
    setViewport(900)
    const { unmount } = render(
      <ResponsiveTable rows={rows} columns={columns} rowKey={(r) => r.id} caption="Models" />,
    )
    expect(screen.getByRole("table", { name: "Models" })).toBeInTheDocument()
    unmount()
    setViewport(390)
    render(<ResponsiveTable rows={rows} columns={columns} rowKey={(r) => r.id} caption="Models" />)
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
    expect(screen.getAllByRole("listitem")).toHaveLength(2)
    expect(screen.getByText("claude-mini")).toBeInTheDocument()
  })
})

describe("EmptyState and AnimatedNumber", () => {
  it("shows title, sentence and action", () => {
    render(<EmptyState title="Nothing yet" description="Add one." action={<button>Add</button>} />)
    expect(screen.getByText("Nothing yet")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Add" })).toBeInTheDocument()
  })

  it("renders a formatted number as plain text", () => {
    render(
      <MotionProvider>
        <AnimatedNumber value={1234.5} format={(v) => `$${v.toFixed(2)}`} />
      </MotionProvider>,
    )
    expect(screen.getByText("$1234.50")).toBeInTheDocument()
  })
})
