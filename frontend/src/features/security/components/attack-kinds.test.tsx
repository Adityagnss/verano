import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { describe, expect, it } from "vitest"

import type { AttackFamilyOut } from "@/lib/api/types"

import { AttackKinds } from "./attack-kinds"

const families = [
  {
    id: "jailbreak",
    title: "Jailbreak",
    owasp: "LLM01",
    description: "Tricks to break the rules.",
    safe_behaviour: "Refuses politely.",
    needs_tools: false,
    built_in_cases: 5,
  },
  {
    id: "pii_extraction",
    title: "Personal data extraction",
    owasp: "LLM02",
    description: "Asks for emails.",
    safe_behaviour: "Declines.",
    needs_tools: false,
    built_in_cases: 5,
  },
] as AttackFamilyOut[]

function Harness() {
  const [selected, setSelected] = useState(new Set(["jailbreak"]))
  return <AttackKinds families={families} selected={selected} onChange={setSelected} />
}

describe("AttackKinds", () => {
  it("selects all and none", async () => {
    const user = userEvent.setup()
    render(<Harness />)
    expect(screen.getByText("1 of 2 kinds selected")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Select all" }))
    expect(screen.getByText("2 of 2 kinds selected")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Select none" }))
    expect(screen.getByText("0 of 2 kinds selected")).toBeInTheDocument()
  })

  it("shows the OWASP tag and expands to the example", async () => {
    const user = userEvent.setup()
    render(<Harness />)
    expect(screen.getByText("OWASP LLM01")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: /Jailbreak/ }))
    expect(await screen.findByText("What the attacker tries")).toBeInTheDocument()
  })
})
