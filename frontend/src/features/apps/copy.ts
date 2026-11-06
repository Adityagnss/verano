/** User-facing text for connecting your own app. */

export const APPS_COPY = {
  title: "Test your own app",
  subtitle:
    "Point Verano at your app's address. It sends each test case, then scores the answer, the text your app retrieved and the tools it called.",
  empty: "No app connected yet.",
  addTitle: "Connect an app",
  addDescription:
    "Where the app is, what to send it, and where in its reply the answer is. Try one test case before you run.",
  fields: {
    name: "Name",
    url: "Address",
    urlHint:
      "For example https://my-app.example.com/ask. Addresses inside your network are refused unless the server owner allows them.",
    template: "What to send",
    templateHint:
      "JSON. Write {{ name | tojson }} where a test case's input goes, using the same names as your prompt's variables.",
    answerPath: "Where is the answer?",
    answerHint: "For example $.answer",
    chunksPath: "Where is the retrieved text? (optional)",
    chunksHint: "For example $.sources[*].text",
    toolCallsPath: "Where are the tool calls? (optional)",
    toolCallsHint: "For example $.tool_calls",
    auth: "Sign-in",
    bearer: "Bearer token",
    basicUser: "Username",
    basicPassword: "Password",
    headerName: "Header name",
    headerValue: "Header value",
    conversation: "Talk to it turn by turn with a simulated user (a judge model plays the user)",
  },
  authKinds: {
    none: "None",
    bearer: "Bearer token",
    basic: "Username and password",
    headers: "Custom header",
  },
  add: "Connect app",
  adding: "Connecting…",
  remove: "Remove",
  secretNote: "Secrets are stored encrypted and never shown again.",
  testTitle: "Send one test case",
  testHint: "Fill in the inputs your request uses, one per line as name=value. Nothing is stored.",
  testInputs: "Inputs",
  testSend: "Send it",
  sending: "Sending…",
  sent: "What was sent",
  received: (status: number | null, ms: number | null) =>
    `What came back${status !== null ? ` (status ${status}${ms !== null ? `, ${ms} ms` : ""})` : ""}`,
  read: "What Verano read",
  answer: "Answer",
  chunks: "Retrieved text",
  toolCalls: "Tool calls",
  truncated: "The reply was longer than the limit and was cut.",
  mode: (mode: string) => (mode === "conversation" ? "conversation" : "one reply"),
}
