/**
 * "What to fill and why" for every step (shown under each step's title), and the content of
 * the Prompt guide page. The technique facts come from the measurements in
 * https://ranjankumar.in/prompt-engineering (small local models, September 2026) and are
 * also written into the Improve step's instructions (backend/app/modules/assistant/prompts/
 * technique_notes.md); keep the two in step.
 */
import type { StepKey } from "./steps"

export type GuideField = { name: string; put: string; why: string; example?: string }
export type StepGuide = { intro: string; fields: GuideField[]; tip?: string }

export const STEP_GUIDES: Record<StepKey, StepGuide> = {
  keys: {
    intro: "Verano calls the models for you, so it needs your key for each provider you want to compare.",
    fields: [
      {
        name: "Provider key",
        put: "Pick a provider (OpenAI, Anthropic, Google …) and paste its API key.",
        why: "Verano uses it to send your prompt to that provider's models. It is stored encrypted and only the last 4 characters are ever shown.",
        example: "sk-proj-… (from your provider's dashboard)",
      },
      {
        name: "Models to test",
        put: "Tick two or three models, then press “Use selected models”.",
        why: "The same prompt runs on each one, so you see which gives the best answers, at what cost and speed.",
        example: "One cheap model, one strong model, one from another provider",
      },
    ],
    tip: "Use the filters to narrow hundreds of models by provider, price, context size or JSON support.",
  },
  prompt: {
    intro:
      "The prompt is the instruction you want to test. Everything else in Verano exists to measure how well it works.",
    fields: [
      {
        name: "Prompt name",
        put: "A short label for you.",
        why: "It only helps you find the prompt later; models never see it.",
        example: "Ordered matching rule",
      },
      {
        name: "System prompt",
        put: "The instructions: who the model is, the rules, and exactly what the answer must look like.",
        why: "This is what you are testing and later improving. If you only write this box, every input file is sent as the user message.",
        example:
          "You draft ordered-matching rules. Reply only with JSON: rule_name, filter, grouping_columns …",
      },
      {
        name: "User prompt (optional)",
        put: "The message sent for each test case. Use {{ name }} where something changes per case; {{ attachment }} is the input file.",
        why: "Skip it when your input file is the whole message. Use it when you want text around the file.",
        example: "Here is the table:\n{{ attachment }}\nDraft the rule.",
      },
      {
        name: "Temperature",
        put: "0 for the same answer every time, higher for more variety.",
        why: "Tests are easier to compare when answers do not change from run to run.",
        example: "0",
      },
      {
        name: "Max reply tokens",
        put: "The longest answer you will allow.",
        why: "Too small and long JSON gets cut off mid-answer, which counts as a failure.",
        example: "1500",
      },
    ],
    tip: "The panel on the right shows how each model will see your prompt and whether it fits their context window.",
  },
  data: {
    intro: "Your own files are the most realistic tests. Everything here is optional.",
    fields: [
      {
        name: "Input files",
        put: "The files your prompt works on. Each file is one test case, sent whole to every model.",
        why: "Real inputs show real behaviour. Spreadsheets are summarised automatically (column types, counts, sample rows).",
        example: "SEP_15_GL_extract.xlsx",
      },
      {
        name: "Golden set",
        put: "The correct answer for each input file, in the same order. Upload it after the input files.",
        why: "It is how Verano scores the models: their answer is compared with yours. Without it you still see every answer, just not a score.",
        example: "goldenset.json with the correct rule",
      },
      {
        name: "Reference documents",
        put: "Policies, manuals or FAQs.",
        why: "Extra test cases are written from them and answers are checked against them.",
        example: "refund-policy.pdf",
      },
    ],
    tip: "With no data at all, choose “generate it for me” and Verano writes the test cases from your prompt.",
  },
  tests: {
    intro:
      "Verano turns your prompt and files into an approved set of test cases and decides how answers are scored.",
    fields: [
      {
        name: "Describe the task",
        put: "Check the short card Verano writes: task type, answer format, goal, rules.",
        why: "It decides which checks score the answers (exact match, JSON checks, an AI judge). A wrong card means wrong scoring.",
        example: "Extraction · JSON · “Draft an ordered-matching rule”",
      },
      {
        name: "How many test cases",
        put: "5 or more. Your own files count towards the number.",
        why: "Only the gaps are generated. Tick “Use only my files” to test on your data alone.",
        example: "10",
      },
      {
        name: "Review and approve",
        put: "Look over the cases, fix or delete any, then approve.",
        why: "Approving freezes the set so every model and every prompt version is tested on exactly the same cases.",
      },
      {
        name: "How answers will be scored",
        put: "Read each card; edit an AI judge's criteria if you want.",
        why: "Rule checks are exact and free. AI judges cost a little and need criteria that say what a good answer looks like.",
        example: "A good answer names every field in the golden rule",
      },
    ],
  },
  run: {
    intro: "Run sends every approved test case to every model you include and stores each answer.",
    fields: [
      {
        name: "Models and runs",
        put: "Untick models to leave out, and set how many times each runs.",
        why: "Running twice or more shows how consistent a model is: the same case can pass once and fail the next time.",
        example: "2 runs",
      },
      {
        name: "Temperature and max tokens",
        put: "Leave the prompt's defaults, or override per model.",
        why: "Some models need a bigger reply limit to finish their JSON.",
      },
      {
        name: "Budget cap (optional)",
        put: "A dollar amount to stop at.",
        why: "The run stops when it has spent this much; finished results are kept.",
        example: "2.00",
      },
    ],
    tip: "The cost preview is an estimate; nothing is spent until you press Start experiment.",
  },
  results: {
    intro:
      "Compare the models on quality, cost and speed, and open any case to see every model's answer side by side.",
    fields: [
      {
        name: "Quality and Passed",
        put: "Nothing to fill in: read the table.",
        why: "Quality is the average score. Passed is the share of cases where every required check passed.",
      },
      {
        name: "How consistent",
        put: "Needs 2 or more runs.",
        why: "A model that passes sometimes is riskier than one that always does.",
      },
      {
        name: "Cost and time",
        put: "Compare per-call cost and average time.",
        why: "The best model is often not the best value. The tiles show the winner of each measure.",
      },
    ],
  },
  improve: {
    intro:
      "Verano studies why cases failed, writes 3 better prompts and proves the best one on cases it never used to write them.",
    fields: [
      {
        name: "Improve from",
        put: "Pick the experiment to learn from.",
        why: "Candidates are written from that experiment's failures.",
      },
      {
        name: "Candidates",
        put: "Read what each one changed (green added, red removed).",
        why: "Each candidate uses a different technique. See the Prompt guide for which techniques really help.",
      },
      {
        name: "Accept as new version",
        put: "Only when the held-back check says it really beat your prompt.",
        why: "Held-back cases were never used to write the candidates, so the check is fair. Accepting saves a new prompt version and the loop can start again.",
      },
    ],
  },
}

export type Verdict = "use" | "measure" | "skip"
export type Technique = {
  name: string
  what: string
  when: string
  effect: string
  verdict: Verdict
  example: string
}

export const LAYERS = [
  {
    name: "Instruction",
    text: "The task, the rules and the output format. This is where most advice is aimed.",
    moves: "Wording, constraints, step-by-step reasoning, personas",
  },
  {
    name: "Examples",
    text: "Worked demonstrations shown before the real question. They teach the task and fix the output format.",
    moves: "How many, which ones, what order",
  },
  {
    name: "Input",
    text: "The documents and the question. The order you place things in changes what the model can use.",
    moves: "Context first, question last, clear delimiters",
  },
  {
    name: "Output format",
    text: "The schema and settings that constrain the answer while it is being written.",
    moves: "JSON schema and key order, temperature, reasoning budget",
  },
]

export const TECHNIQUES: Technique[] = [
  {
    name: "State the exact output format",
    what: "Say what the answer must look like: the format, the allowed values, one-line rules.",
    when: "Always, especially when answers come back in the wrong shape.",
    effect: "The most reliable fix for broken formats.",
    verdict: "use",
    example: "Reply with one lowercase word: billing, shipping, technical or other.",
  },
  {
    name: "Reasoning first in JSON",
    what: "In a JSON answer, put the reasoning field before the answer field.",
    when: "Whenever the answer needs several steps of thought.",
    effect: "About +39 points against answer-first order in the tutorial's tests.",
    verdict: "use",
    example: '{"reasoning": "…", "answer": 42}',
  },
  {
    name: "Chain of thought",
    what: "Ask the model to work step by step, then give a marked final answer.",
    when: "Multi-step problems on plain (non-reasoning) models. Not for classification or lookup.",
    effect: "Large gains on plain models; extra cost and sometimes worse on reasoning models.",
    verdict: "measure",
    example: "Work through it step by step, then end with: Answer: <value>",
  },
  {
    name: "Few-shot examples",
    what: "Show 2 to 4 solved examples before the real question.",
    when: "When the format or the pattern is unclear. Use examples close to your failures.",
    effect: "Varies by model; helps small models more than large ones.",
    verdict: "measure",
    example: "Ticket: “charged twice” → billing",
  },
  {
    name: "Context first, question last",
    what: "Put reference material before the question and delimit it.",
    when: "Whenever the answer depends on supplied text.",
    effect: "Conditional; the model can only use what it has already read.",
    verdict: "measure",
    example: "<document>…</document> Question: …",
  },
  {
    name: "Expert persona",
    what: "“You are a world-class expert …”",
    when: "To set tone or register only.",
    effect: "No reliable accuracy gain.",
    verdict: "skip",
    example: "You are a brilliant expert who never makes errors.",
  },
  {
    name: "Politeness and offered rewards",
    what: "“Please”, “thank you”, “I will tip $200”.",
    when: "Never for accuracy.",
    effect: "No measured effect; wastes tokens.",
    verdict: "skip",
    example: "I’ll tip $200 for a correct answer.",
  },
  {
    name: "Asking it to check itself",
    what: "“Review your answer and fix mistakes” with no new information.",
    when: "Not without a real check to compare against.",
    effect: "Did not help, and sometimes made answers worse.",
    verdict: "skip",
    example: "Double-check your answer.",
  },
]

export const RULES = [
  "Measure on your own task. The published numbers show the method, not what will happen for you.",
  "Compare the gap with the spread. A difference smaller than run-to-run variation is noise, so run each prompt more than once.",
  "Change one thing at a time, so you know which change helped.",
  "Check the model type. Reasoning models often react the opposite way to plain models.",
  "Watch for cut-off answers. Long reasoning needs a large reply limit.",
]
