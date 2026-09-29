/** User-facing text for the Prompt step. */
export const PROMPT_COPY = {
  title: "Write the prompt to test",
  subtitle:
    "Fill in a system prompt, a user prompt, or both. Use {{ name }} for anything that changes per test case, for example {{ ticket }}.",
  howItWorks: [
    "Write the instructions (system prompt), the message per case (user prompt), or both.",
    "Put anything that changes per case in {{ double braces }}, e.g. {{ ticket }}.",
    "The prompt check shows what each case needs and if it fits each model.",
    "Saving keeps every version, so you can always compare or go back.",
  ],
  editorHeading: "Your prompt",
  editorHint: "At least one of the two boxes must be filled.",
  versionBadge: (n: number) => `Version ${n}`,
  reviewHint: "Updates as you type.",
  name: "Prompt name",
  namePlaceholder: "e.g. Ticket triage",
  system: "System prompt",
  systemHint: "Instructions for the model. Optional if you write a user prompt.",
  user: "User prompt",
  userHint:
    "The message sent for each test case, with its {{ variables }}. Optional if you write a system prompt.",
  parameters: "Default parameters",
  temperature: "Temperature",
  maxTokens: "Max reply tokens",
  changeReason: "What changed (optional)",
  review: "Prompt check",
  reviewEmpty: "Start writing and the checks appear here.",
  shape: {
    system_and_user: "System and user prompt: each test case fills the variables.",
    system_only: "System prompt only: each test case is sent as the user message.",
    user_only: "User prompt only: each test case fills the variables, no system message.",
  } as Record<string, string>,
  variables: (names: string[]) => (names.length ? `Variables: ${names.join(", ")}` : "No variables"),
  inputsNeeded: (names: string[]) =>
    names.length === 1 && names[0] === "user_message"
      ? "Each input file is sent to the model as the user message."
      : `Each test case needs: ${names.join(", ")}. An input file fills {{ attachment }}.`,
  fits: (model: string, tokens: number) => `Fits ${model} (about ${tokens.toLocaleString()} tokens)`,
  fitsAll: (count: number, tokens: number) =>
    `Fits all ${count} selected models (about ${tokens.toLocaleString()} tokens)`,
  showAll: "Show all",
  showLess: "Show less",
  characters: (count: number) => `${count.toLocaleString()} characters`,
  tooLong: (model: string, tokens: number) =>
    `Too long for ${model} (about ${tokens.toLocaleString()} tokens)`,
  unknownWindow: (model: string) => `${model}: context size unknown`,
  noModels: "Select models in step 1 to check the context size.",
  preview: "Preview with your first test case",
  version: (n: number) => `Saved as version ${n}`,
  save: "Save prompt",
  saveVersion: "Save new version",
  saving: "Saving…",
  unchanged: "No changes since the last version.",
  next: "Next: your data",
}
