/** Pure helpers for the apps screens: templates, the request preview and plain-language readings of a test. */
import type { AppTargetCreate } from "@/lib/api/types"

export type AuthKind = "none" | "bearer" | "basic" | "headers"

/** "name=value" lines into the inputs of one test case; a line without "=" is ignored. */
export function parseInputs(text: string): Record<string, string> {
  const inputs: Record<string, string> = {}
  for (const line of text.split("\n")) {
    const at = line.indexOf("=")
    if (at > 0) inputs[line.slice(0, at).trim()] = line.slice(at + 1)
  }
  return inputs
}

export type TemplateId = "chat" | "openai" | "rag" | "custom"

export interface AppTemplate {
  id: TemplateId
  title: string
  description: string
  requestTemplate: string
  answerPath: string
  chunksPath: string
  toolCallsPath: string
}

export const TEMPLATES: AppTemplate[] = [
  {
    id: "chat",
    title: "Chat app with a question",
    description: "You send a question and get an answer back.",
    requestTemplate: '{"question": {{ question | tojson }}}',
    answerPath: "$.answer",
    chunksPath: "",
    toolCallsPath: "",
  },
  {
    id: "openai",
    title: "OpenAI-style chat",
    description: "Takes a list of messages and returns choices, like the OpenAI chat API.",
    requestTemplate:
      '{"model": "my-app", "messages": [{"role": "user", "content": {{ question | tojson }}}]}',
    answerPath: "$.choices[0].message.content",
    chunksPath: "",
    toolCallsPath: "$.choices[0].message.tool_calls",
  },
  {
    id: "rag",
    title: "RAG app that returns sources",
    description: "Answers from your documents and sends back the text it found.",
    requestTemplate: '{"question": {{ question | tojson }}}',
    answerPath: "$.answer",
    chunksPath: "$.sources[*].text",
    toolCallsPath: "",
  },
  {
    id: "custom",
    title: "Custom JSON",
    description: "Write the request yourself and say where the answer is.",
    requestTemplate: '{"question": {{ question | tojson }}}',
    answerPath: "$.answer",
    chunksPath: "",
    toolCallsPath: "",
  },
]

export interface AppDraft {
  name: string
  url: string
  template: TemplateId
  requestTemplate: string
  answerPath: string
  chunksPath: string
  toolCallsPath: string
  auth: AuthKind
  bearer: string
  user: string
  password: string
  headerName: string
  headerValue: string
  conversation: boolean
  timeout: string
}

export function emptyDraft(): AppDraft {
  const t = TEMPLATES[0]
  return {
    name: "",
    url: "",
    template: t.id,
    requestTemplate: t.requestTemplate,
    answerPath: t.answerPath,
    chunksPath: t.chunksPath,
    toolCallsPath: t.toolCallsPath,
    auth: "none",
    bearer: "",
    user: "",
    password: "",
    headerName: "",
    headerValue: "",
    conversation: false,
    timeout: "",
  }
}

export function applyTemplate(draft: AppDraft, id: TemplateId): AppDraft {
  const t = TEMPLATES.find((x) => x.id === id) ?? TEMPLATES[0]
  return {
    ...draft,
    template: t.id,
    requestTemplate: t.requestTemplate,
    answerPath: t.answerPath,
    chunksPath: t.chunksPath,
    toolCallsPath: t.toolCallsPath,
  }
}

/** Why the address cannot be used yet, or null when it looks fine. */
export function addressProblem(url: string): string | null {
  const text = url.trim()
  if (!text) return "Enter your app's address, for example https://my-app.example.com/ask."
  try {
    const parsed = new URL(text)
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:")
      return "The address must start with http:// or https://."
  } catch {
    return "That does not look like an address. It should look like https://my-app.example.com/ask."
  }
  return null
}

/** A name for the app: the one typed, or the host of its address. */
export function appName(draft: AppDraft): string {
  if (draft.name.trim()) return draft.name.trim()
  try {
    return new URL(draft.url.trim()).host
  } catch {
    return "My app"
  }
}

/** The body for saving the draft (also valid as an update: every field is optional there). */
export function toCreateBody(draft: AppDraft): AppTargetCreate {
  const timeout = Number(draft.timeout)
  return {
    name: appName(draft),
    url: draft.url.trim(),
    method: "POST",
    request_template: draft.requestTemplate,
    answer_path: draft.answerPath.trim(),
    chunks_path: draft.chunksPath.trim() || null,
    tool_calls_path: draft.toolCallsPath.trim() || null,
    mode: draft.conversation ? "conversation" : "single",
    auth_kind: draft.auth,
    ...(draft.auth === "bearer" && draft.bearer ? { bearer_token: draft.bearer } : {}),
    ...(draft.auth === "basic" && draft.password
      ? { basic_username: draft.user, basic_password: draft.password }
      : {}),
    headers: draft.auth === "headers" && draft.headerName ? { [draft.headerName]: draft.headerValue } : {},
    ...(timeout > 0 ? { timeout_s: timeout } : {}),
  }
}

/** The variable names a request template uses, in order: `{{ question | tojson }}` gives "question". */
export function templateVariables(template: string): string[] {
  const found: string[] = []
  for (const match of template.matchAll(/\{\{\s*([A-Za-z_]\w*)/g)) {
    if (!found.includes(match[1])) found.push(match[1])
  }
  return found
}

/** A sample input for each variable, as "name=value" lines. */
export function sampleInputs(template: string, value = "What can you help me with?"): string {
  const names = templateVariables(template)
  return (names.length ? names : ["question"]).map((n) => `${n}=${value}`).join("\n")
}

/** The request body that will be sent for sample inputs: the template filled in, pretty-printed when JSON. */
export function previewRequest(template: string, inputs: Record<string, string>): string {
  const filled = template.replace(
    /\{\{\s*([A-Za-z_]\w*)\s*(\|\s*tojson\s*)?\}\}/g,
    (_all, name: string, json: string | undefined) => {
      const value = inputs[name] ?? ""
      return json ? JSON.stringify(value) : value
    },
  )
  try {
    return JSON.stringify(JSON.parse(filled), null, 2)
  } catch {
    return filled
  }
}

export interface CheckReading {
  ok: boolean
  headline: string
  fix: string | null
}

interface TestLike {
  error: string | null
  latency_ms: number | null
  status_code: number | null
}

/** A plain-language reading of one test: worked or not, how long it took, and what to fix. */
export function readCheck(result: TestLike): CheckReading {
  const status = result.status_code
  if (result.error && status === null) {
    return {
      ok: false,
      headline: "Verano could not reach your app.",
      fix: `Check the address and that the app is running and reachable from the server. Detail: ${result.error}`,
    }
  }
  if (status === 401 || status === 403) {
    return {
      ok: false,
      headline: `Your app refused the request (status ${status}).`,
      fix: "It wants a sign-in. Open Advanced on the next step and add the key or token your app expects.",
    }
  }
  if (status === 404) {
    return {
      ok: false,
      headline: "Your app answered, but not at this address (status 404).",
      fix: "Check the path at the end of the address, for example /ask or /v1/chat.",
    }
  }
  if (status !== null && status >= 400) {
    return {
      ok: false,
      headline: `Your app returned an error (status ${status}).`,
      fix: "Look at your app's logs. If the request looks wrong, change what is sent on the next step.",
    }
  }
  if (result.error) {
    return {
      ok: false,
      headline: "Your app answered, but Verano could not read the answer.",
      fix: `${result.error} Change where the answer is on the next step.`,
    }
  }
  const ms = result.latency_ms
  return {
    ok: true,
    headline: ms !== null ? `Connected. Your app answered in ${ms} ms.` : "Connected. Your app answered.",
    fix: null,
  }
}

/** One-line explanations of what Verano read from a reply. */
export function explainReading(
  reply: { answer: string; chunks: string[]; tool_calls: unknown[] },
  answerPath: string,
): string[] {
  const lines = [
    reply.answer
      ? `The answer was taken from ${answerPath} and is what the judge will score.`
      : `Nothing was found at ${answerPath}, so there is no answer to score. Change where the answer is.`,
  ]
  if (reply.chunks.length)
    lines.push(`Found ${reply.chunks.length} retrieved text(s), used to check the answer is grounded.`)
  if (reply.tool_calls.length)
    lines.push(`Found ${reply.tool_calls.length} tool call(s), used to check the right tools ran.`)
  return lines
}
