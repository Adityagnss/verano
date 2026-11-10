import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

import { ConnectWizard } from "./connect-wizard"

function setup() {
  const client = new QueryClient()
  render(
    <QueryClientProvider client={client}>
      <ConnectWizard projectId="p1" onDone={vi.fn()} onCancel={vi.fn()} />
    </QueryClientProvider>,
  )
}

describe("ConnectWizard", () => {
  it("asks only for the address on the first step and blocks Next without one", async () => {
    setup()
    const user = userEvent.setup()
    expect(screen.getByLabelText("Address")).toBeInTheDocument()
    expect(screen.queryByLabelText("Where is the answer?")).toBeNull()
    await user.click(screen.getByRole("button", { name: "Check connection" }))
    expect(await screen.findByText(/Enter your app's address/)).toBeInTheDocument()
  })

  it("explains a malformed address", async () => {
    setup()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText("Address"), "not an address")
    await user.click(screen.getByRole("button", { name: "Check connection" }))
    expect(await screen.findByText(/does not look like an address/)).toBeInTheDocument()
  })
})
