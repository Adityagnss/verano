import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { Wizard } from "./wizard"

function setup(valid: boolean) {
  const onFinish = vi.fn()
  render(
    <Wizard
      finishLabel="Create"
      onFinish={onFinish}
      steps={[
        {
          id: "a",
          title: "First",
          content: <p>first body</p>,
          validate: () => (valid ? true : "Fill this in."),
        },
        { id: "b", title: "Second", content: <p>second body</p> },
      ]}
    />,
  )
  return onFinish
}

describe("Wizard", () => {
  it("blocks Next with the validation message", async () => {
    const user = userEvent.setup()
    setup(false)
    await user.click(screen.getByRole("button", { name: "Next" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Fill this in.")
    expect(screen.getByText("first body")).toBeInTheDocument()
  })

  it("moves forward, back, and finishes", async () => {
    const user = userEvent.setup()
    const onFinish = setup(true)
    await user.click(screen.getByRole("button", { name: "Next" }))
    expect(await screen.findByText("second body")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Back" }))
    expect(await screen.findByText("first body")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Next" }))
    await screen.findByText("second body")
    await user.click(screen.getByRole("button", { name: "Create" }))
    expect(onFinish).toHaveBeenCalledOnce()
  })
})
