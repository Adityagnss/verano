import { describe, expect, it } from "vitest"

import { envLines, snippets, TESTED_WITH } from "./snippets"

describe("snippets", () => {
  it("puts the three variables in every environment block", () => {
    const lines = envLines("http://x/v1/traces", "tok")
    expect(lines[0]).toBe("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://x/v1/traces")
    expect(lines[1]).toBe("OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer tok")
    expect(lines[2]).toBe("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf")
  })
  it("has Python, Node and curl with the token", () => {
    const list = snippets("http://x/v1/traces", "tok")
    expect(list.map((s) => s.id)).toEqual(["python", "node", "curl"])
    for (const s of list) expect(s.code).toContain("tok")
  })
  it("is honest about what was checked", () => {
    expect(TESTED_WITH).toMatch(/OpenInference and OpenLLMetry only/)
  })
})
