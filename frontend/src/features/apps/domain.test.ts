import { describe, expect, it } from "vitest"

import { parseInputs } from "./domain"

describe("parseInputs", () => {
  it("reads name=value lines and keeps an equals sign inside a value", () => {
    expect(parseInputs("question=How long?\nq2=a=b")).toEqual({ question: "How long?", q2: "a=b" })
  })

  it("ignores lines that have no name or no equals sign", () => {
    expect(parseInputs("just text\n=nothing\n\nok=1")).toEqual({ ok: "1" })
  })
})

import { addressProblem, applyTemplate, emptyDraft, previewRequest, readCheck, sampleInputs } from "./domain"

describe("templates and preview", () => {
  it("fills the request with sample inputs", () => {
    const draft = emptyDraft()
    const body = previewRequest(draft.requestTemplate, parseInputs(sampleInputs(draft.requestTemplate, "Hi")))
    expect(JSON.parse(body)).toEqual({ question: "Hi" })
  })
  it("choosing a RAG template sets the sources path", () => {
    expect(applyTemplate(emptyDraft(), "rag").chunksPath).toBe("$.sources[*].text")
  })
  it("rejects bad addresses", () => {
    expect(addressProblem("")).not.toBeNull()
    expect(addressProblem("ftp://x")).not.toBeNull()
    expect(addressProblem("https://a.example/ask")).toBeNull()
  })
  it("reads failures in plain words", () => {
    expect(readCheck({ error: null, latency_ms: 40, status_code: 200 }).ok).toBe(true)
    expect(readCheck({ error: null, latency_ms: 40, status_code: 401 }).headline).toMatch(/refused/)
    expect(readCheck({ error: "refused", latency_ms: null, status_code: null }).headline).toMatch(
      /could not reach/,
    )
  })
})
