import { describe, expect, it } from "vitest"

import { suggestVariables, variableProblems } from "./variables"

describe("mapping columns to prompt variables", () => {
  it("pre-picks a column with the same name", () => {
    expect(suggestVariables(["customer_name", "message"], ["Message", "Customer Name", "id"])).toEqual({
      customer_name: "Customer Name",
      message: "Message",
    })
  })

  it("asks for every variable that has no column", () => {
    expect(variableProblems(["a", "b"], { a: "x" })).toEqual(["Pick the column that fills {{b}}."])
  })
})
