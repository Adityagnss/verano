import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import type { ModelMetricsOut } from "@/lib/api/types"

import { SummaryTab } from "./summary-tab"

const m = (id: string, quality: number, vs: string | null) =>
  ({
    model_profile_id: id,
    model: id,
    quality,
    cost_per_call: 0.002,
    latency_ms: 300,
    cases: 5,
    failed_calls: 0,
    vs_best: vs ? { label: vs } : null,
  }) as unknown as ModelMetricsOut

describe("SummaryTab", () => {
  it("names the winner and says it is clearly better", () => {
    render(
      <SummaryTab
        projectId="p1"
        experimentId="e1"
        models={[m("alpha", 0.9, null), m("beta", 0.4, "clear difference")]}
        ranked
        scored
      />,
    )
    expect(screen.getByTestId("winner-card")).toHaveTextContent("alpha")
    expect(screen.getByText(/Clearly better/)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Improve the prompt" })).toHaveAttribute(
      "href",
      "/projects/p1/improve?experiment=e1",
    )
    expect(screen.getByRole("link", { name: "Label answers" })).toBeInTheDocument()
  })
  it("names no winner when the runs are not alike", () => {
    render(
      <SummaryTab projectId="p1" experimentId="e1" models={[m("alpha", 0.9, null)]} ranked={false} scored />,
    )
    expect(screen.getByText(/not a fair comparison/)).toBeInTheDocument()
  })
})
