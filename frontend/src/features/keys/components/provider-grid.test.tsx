import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import type { CredentialOut, ProviderOut } from "@/lib/api/types"

import { ProviderGrid } from "./provider-grid"

const providers = [
  { name: "openai", display_name: "OpenAI", requires_key: true, free: false },
  { name: "ollama", display_name: "Ollama (local)", requires_key: false, free: true },
] as unknown as ProviderOut[]

describe("ProviderGrid", () => {
  it("shows which providers are connected and how many models they reach", () => {
    const credentials = [{ provider: "openai", model_count: 3 }] as unknown as CredentialOut[]
    render(<ProviderGrid providers={providers} credentials={credentials} onAdd={vi.fn()} />)
    expect(screen.getByText("Connected · 3 models")).toBeInTheDocument()
    expect(screen.getByText("Free · local")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Add key/ })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Connect/ })).toBeInTheDocument()
  })

  it("says so when nothing is connected", () => {
    render(<ProviderGrid providers={providers.slice(0, 1)} onAdd={vi.fn()} />)
    expect(screen.getByText("Not connected")).toBeInTheDocument()
  })
})
