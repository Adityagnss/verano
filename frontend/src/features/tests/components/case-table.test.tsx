import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import type { ItemOut } from "@/lib/api/types"
import { setViewport } from "@/test/viewport"

import { CaseTable } from "./case-table"

function item(id: string, review_status: string): ItemOut {
  return {
    id,
    inputs: { text: `input ${id}` },
    context: [],
    source: "generated",
    category: "happy_path",
    review_status,
    expected_output: "billing",
    rubric: [],
  } as unknown as ItemOut
}

function show(items: ItemOut[]) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <CaseTable projectId="p" versionId="v" items={items} frozen={false} />
    </QueryClientProvider>,
  )
}

describe("case table", () => {
  it("filters by review status and uses cards on a phone", async () => {
    setViewport(390)
    show([item("a", "draft"), item("b", "approved")])
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
    expect(screen.getByText("input a")).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: "Reviewed" }))
    expect(screen.queryByText("input a")).not.toBeInTheDocument()
    expect(screen.getByText("input b")).toBeInTheDocument()
  })

  it("shows a table on wide screens", () => {
    setViewport(1280)
    show([item("a", "draft")])
    expect(screen.getByRole("table")).toBeInTheDocument()
  })
})
