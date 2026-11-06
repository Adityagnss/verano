/** Pure rules for adding checks: reading a rule's settings, building the check to save, naming. No React here. */
import type { EvaluatorConfigIn, EvaluatorSetVersionOut } from "@/lib/api/types"

export type FieldKind = "text" | "lines" | "number" | "bool" | "json"

export type RuleField = {
  name: string
  kind: FieldKind
  /** The text in brackets of the rule's description, for example "default false". */
  hint: string
  required: boolean
}

const KINDS: Record<string, FieldKind> = {
  values: "lines",
  names: "lines",
  allowed_outputs: "lines",
  constraints: "lines",
  case_sensitive: "bool",
  relative: "bool",
  min: "number",
  max: "number",
  limit: "number",
  tolerance: "number",
  min_times: "number",
  output_schema: "json",
  arguments: "json",
}

/** Closeness measures give a 0 to 1 value, so they need a pass mark below 1; the rest are yes or no. */
const SOFT_RULES = new Set([
  "token_overlap_f1",
  "edit_similarity",
  "bleu",
  "rouge_l",
  "field_match",
  "contains_all",
])

export const defaultThreshold = (rule: string): number => (SOFT_RULES.has(rule) ? 0.5 : 1)

/** Splits "values (list), case_sensitive (default false)" on the commas outside brackets. */
function splitTopLevel(text: string): string[] {
  const parts: string[] = []
  let depth = 0
  let current = ""
  for (const ch of text) {
    if (ch === "(") depth += 1
    if (ch === ")") depth -= 1
    if (ch === "," && depth === 0) {
      parts.push(current.trim())
      current = ""
    } else current += ch
  }
  if (current.trim()) parts.push(current.trim())
  return parts
}

/** The settings of a rule, read from the plain text the server gives ("none" means no settings). */
export function parseSettings(text: string): RuleField[] {
  if (text.trim().toLowerCase() === "none") return []
  return splitTopLevel(text).map((part) => {
    const match = /^([a-z_]+)\s*(?:\((.*)\))?$/i.exec(part)
    const name = match?.[1] ?? part
    const hint = match?.[2] ?? ""
    const kind = KINDS[name] ?? "text"
    const optional = /optional|default/i.test(hint) || kind === "bool"
    return { name, kind, hint, required: !optional }
  })
}

export type RuleValues = Record<string, string | boolean>

export type Built = { config: Record<string, unknown>; errors: string[] }

const label = (name: string) => name.replaceAll("_", " ")

/** The check's settings from what was typed, with every problem named in plain words. */
export function buildRuleConfig(fields: RuleField[], values: RuleValues): Built {
  const config: Record<string, unknown> = { kind: "rule" }
  const errors: string[] = []
  for (const field of fields) {
    const raw = values[field.name]
    const text = typeof raw === "string" ? raw.trim() : ""
    if (field.kind === "bool") {
      if (raw === true) config[field.name] = true
      continue
    }
    if (text === "") {
      if (field.required) errors.push(`Fill in “${label(field.name)}”.`)
      continue
    }
    if (field.kind === "lines") {
      config[field.name] = text
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
    } else if (field.kind === "number") {
      const n = Number(text)
      if (!Number.isFinite(n)) errors.push(`“${label(field.name)}” must be a number.`)
      else config[field.name] = n
    } else if (field.kind === "json") {
      try {
        config[field.name] = JSON.parse(text)
      } catch {
        errors.push(`“${label(field.name)}” is not valid JSON.`)
      }
    } else if (field.name === "flags" && !/^[ism]*$/.test(text)) {
      errors.push("“flags” can only use the letters i, s and m.")
    } else config[field.name] = text
  }
  const low = config.min
  const high = config.max
  if (typeof low === "number" && typeof high === "number" && low > high)
    errors.push("“min” cannot be larger than “max”.")
  return { config, errors }
}

/** The checks already in a set, in the form the server takes back. */
export function currentChecks(set: EvaluatorSetVersionOut): EvaluatorConfigIn[] {
  return set.evaluators.map((e) => ({
    evaluator_name: e.evaluator_name,
    evaluator_version: e.evaluator_version,
    config: e.config as Record<string, unknown>,
    threshold: e.threshold,
    weight: e.weight,
    required: e.required,
  }))
}

export const hasCheck = (set: EvaluatorSetVersionOut, name: string): boolean =>
  set.evaluators.some((e) => e.evaluator_name === name)

/** A short name for a code check, made from what the person called it and never one already taken. */
export function codeCheckName(title: string, taken: string[]): string {
  const slug =
    title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 40) || "check"
  const base = `code_${slug}`
  if (!taken.includes(base)) return base
  let n = 2
  while (taken.includes(`${base}_${n}`)) n += 1
  return `${base}_${n}`
}

export const CODE_TEMPLATE = `def check(case):
    # case["output"] is the model's answer. case["expected"], case["inputs"] and case["rubric"] are also there.
    words = len(case["output"].split())
    # Return a score from 0 to 1 and, if you like, the reason.
    return (1.0 if words <= 50 else 0.0, f"{words} words")
`

/** "Needs: the retrieved text and the expected answer" for a gallery judge. */
export function requirementText(requires: string | null): string | null {
  if (!requires) return null
  const words: Record<string, string> = {
    context: "the text the app retrieved",
    expected: "an expected answer",
    tools: "the tools the app called",
  }
  return requires
    .split(",")
    .map((r) => words[r.trim()] ?? r.trim())
    .join(" and ")
}

/** What the sandbox says about a try, in a sentence. */
export function tryVerdict(result: { ok: boolean; passed: boolean | null; score: number | null }): string {
  if (!result.ok || result.score === null) return "The check could not run."
  const score = `${Math.round(result.score * 100)}%`
  return result.passed ? `Passed, score ${score}.` : `Failed, score ${score}.`
}
