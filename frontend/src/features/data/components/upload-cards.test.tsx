import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { UploadCards } from "./upload-cards"

function wrap(kinds?: ("inputs" | "golden" | "documents")[]) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <UploadCards projectId="p1" kinds={kinds} />
    </QueryClientProvider>,
  )
}

describe("UploadCards", () => {
  it("shows all three kinds by default", () => {
    wrap()
    expect(screen.getByText("Input files")).toBeInTheDocument()
    expect(screen.getByText("Golden set")).toBeInTheDocument()
    expect(screen.getByText("Reference documents")).toBeInTheDocument()
  })

  it("shows only the kinds that were chosen", () => {
    wrap(["golden"])
    expect(screen.getByTestId("upload-golden")).toBeInTheDocument()
    expect(screen.queryByTestId("upload-inputs")).not.toBeInTheDocument()
  })
})
