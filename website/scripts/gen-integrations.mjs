// Generates the Integrations page from integrations/registry.yaml, the one list of integrations, with the status of each
// shown as the registry states it. Evidence under internal paths (verification records) is named but not linked.
import fs from "node:fs"
import path from "node:path"
import YAML from "yaml"
import { ROOT, WEBSITE, REPO_URL, BRANCH, cell, isPrivate, read, writePage } from "./lib.mjs"

const SOURCE = "integrations/registry.yaml"
const registry = YAML.parse(read(SOURCE))
const STATUS = {
  validated: "Validated",
  sample_tested: "Sample-tested",
  built: "Built",
  planned: "Planned",
}
const GROUPS = {
  native_sdk: "Native SDKs",
  framework_adapter: "Framework adapters",
  observability_import: "Observability imports",
  ci_integration: "CI integrations",
}

// Logos ship with the site (copied from the repository), never loaded from elsewhere.
const logoDir = path.join(WEBSITE, "public", "logos")
fs.mkdirSync(logoDir, { recursive: true })
const logoSrc = path.join(ROOT, "integrations/logos")
for (const f of fs.readdirSync(logoSrc)) if (f.endsWith(".svg")) fs.copyFileSync(path.join(logoSrc, f), path.join(logoDir, f))

const counts = Object.fromEntries(Object.keys(STATUS).map((s) => [s, registry.integrations.filter((i) => i.status === s).length]))
const badge = (s) => `<span class="status status-${s.replace("_", "-")}">${STATUS[s]}</span>`
const mark = (i, base) =>
  i.logo
    ? `<img class="int-logo" src="${base}logos/${i.logo}.svg" alt="" width="20" height="20">`
    : `<span class="int-chip">${cell(i.chip ?? "")}</span>`
const link = (ref, text) => (isPrivate(ref) ? text : `[${text}](${REPO_URL}/blob/${BRANCH}/${ref})`)

const lines = [
  "# Integrations",
  "",
  "Every integration below shows what has been checked, not what might work. Nothing is listed because it is only theoretically compatible (for example, through OpenTelemetry): a row needs the evidence for its status.",
  "",
  "- **Validated:** checked against the real third-party tool or library, with the version and date recorded.",
  "- **Sample-tested:** automated tests pass against stand-in objects or sample files we wrote.",
  "- **Built:** the code exists; no automated test of this integration.",
  "- **Planned:** not built.",
  "",
  `Today: ${counts.validated} validated · ${counts.sample_tested} sample-tested · ${counts.built} built · ${counts.planned} planned.`,
  "",
  "None of the packages is published to PyPI or npm yet; where a row says so, install from a clone of the repository.",
  "",
]
for (const [group, title] of Object.entries(GROUPS)) {
  const items = registry.integrations.filter((i) => i.group === group)
  if (!items.length) continue
  lines.push(`## ${title}`, "")
  for (const i of items) {
    lines.push(`### ${cell(i.name)}`, "", `<p class="int-line">${mark(i, "/")}${badge(i.status)}</p>`, "")
    lines.push(cell(i.summary).replace(/`([^`]*)`/g, "`$1`"), "")
    const facts = []
    if (i.where) facts.push(`**Where:** ${link(i.where, `\`${i.where}\``)}`)
    if (i.distribution) facts.push(`**Distribution:** ${cell(i.distribution)}`)
    if (i.verified_with) facts.push(`**Verified with:** ${cell(i.verified_with)}${i.verified_on ? ` on ${i.verified_on}` : ""}`)
    if (facts.length) lines.push(facts.map((f) => `- ${f}`).join("\n"), "")
    if (i.evidence?.length) {
      lines.push("**What shows it:**", "")
      for (const e of i.evidence) {
        const note = e.note ? ` ${cell(e.note)}` : ""
        if (e.kind === "record" || isPrivate(e.ref)) lines.push(`- A verification record kept in the repository.${note}`)
        else lines.push(`- ${link(e.ref, `\`${e.ref.split("/").pop()}\``)}${note ? ` (${note.trim()})` : ""}`)
      }
      lines.push("")
    }
    if (i.next_step) lines.push(`**Next step:** ${cell(i.next_step)}`, "")
  }
}
writePage("reference/integrations.md", lines.join("\n"), { editPath: SOURCE })
console.log(`gen-integrations: ${registry.integrations.length} integrations`)
