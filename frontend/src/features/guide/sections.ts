/**
 * How the one Markdown guide from the server is split into pages. Each page lists the level-2
 * headings it shows; the text itself is never changed. A heading the list does not know goes to
 * the last page, so nothing the server adds is ever lost.
 */

export type GuideSection = {
  slug: string
  title: string
  summary: string
  headings: string[]
}

export const GUIDE_SECTIONS: GuideSection[] = [
  {
    slug: "start-here",
    title: "Start here",
    summary: "What the guide is for, and the one habit that makes the rest work.",
    headings: ["Start here", "The one habit: measure first"],
  },
  {
    slug: "parts-of-a-prompt",
    title: "What a prompt is made of",
    summary: "The parts of a prompt and what each one does.",
    headings: ["What a prompt is made of"],
  },
  {
    slug: "cheat-sheet",
    title: "Cheat sheet",
    summary: "Which technique to use when, with what each costs.",
    headings: ["Cheat sheet: which technique, when", "Use these"],
  },
  {
    slug: "techniques",
    title: "Techniques by purpose",
    summary: "Shape the answer, add reasoning, add information, split the work, check the work.",
    headings: [
      "Techniques that shape the answer",
      "Techniques that add reasoning",
      "Techniques that add information",
      "Techniques that split the work",
      "Techniques that check the work",
      "Reasoning models",
      "Context: what to give the model",
      "AI agents",
    ],
  },
  {
    slug: "scoring",
    title: "Scoring answers",
    summary: "How to decide whether an answer is good.",
    headings: ["Scoring answers"],
  },
  {
    slug: "safety",
    title: "Safety",
    summary: "Attacks to expect, and what not to build a candidate around.",
    headings: ["Safety", "Do not build a candidate around these"],
  },
  {
    slug: "speed-and-cost",
    title: "Speed and cost",
    summary: "Make answers faster and cheaper without losing quality.",
    headings: ["Speed and cost"],
  },
  {
    slug: "templates",
    title: "Templates",
    summary: "Copy-ready prompts to start from.",
    headings: ["Copy-ready templates"],
  },
  {
    slug: "checklist",
    title: "Checklist",
    summary: "What to check before you ship a new prompt version, and a glossary.",
    headings: ["Checklist for a new prompt version", "Glossary"],
  },
]

/** The Markdown split at its level-2 headings (ignoring "## " inside code fences). */
export function splitByHeading(source: string): { title: string; body: string }[] {
  const out: { title: string; lines: string[] }[] = []
  let fenced = false
  for (const line of source.replace(/^# .*\n/, "").split("\n")) {
    if (line.startsWith("```")) fenced = !fenced
    if (!fenced && line.startsWith("## ")) out.push({ title: line.slice(3).trim(), lines: [line] })
    else out.at(-1)?.lines.push(line)
  }
  return out.map((s) => ({ title: s.title, body: s.lines.join("\n").trimEnd() }))
}

/** The Markdown of one guide page. */
export function sectionMarkdown(source: string, section: GuideSection): string {
  const known = new Set(GUIDE_SECTIONS.flatMap((s) => s.headings))
  const last = GUIDE_SECTIONS.at(-1)
  return splitByHeading(source)
    .filter((part) =>
      section.headings.includes(part.title) ? true : section === last && !known.has(part.title),
    )
    .map((part) => part.body)
    .join("\n\n")
}

export function findSection(sectionSlug: string): GuideSection | undefined {
  return GUIDE_SECTIONS.find((s) => s.slug === sectionSlug)
}

export function neighbours(section: GuideSection): { previous?: GuideSection; next?: GuideSection } {
  const index = GUIDE_SECTIONS.indexOf(section)
  return { previous: GUIDE_SECTIONS[index - 1], next: GUIDE_SECTIONS[index + 1] }
}
