// Generates the API reference from the OpenAPI file the frontend client is built from: one page per tag, plus an index.
// Also writes .vitepress/generated/api-sidebar.json for the sidebar.
import fs from "node:fs"
import path from "node:path"
import { ROOT, WEBSITE, REPO_URL, BRANCH, cell, writePage } from "./lib.mjs"

const SOURCE = "frontend/src/lib/api/openapi.json"
const spec = JSON.parse(fs.readFileSync(path.join(ROOT, SOURCE), "utf8"))
const METHODS = ["get", "post", "put", "patch", "delete"]
const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")
const refName = (schema) => {
  if (!schema) return null
  if (schema.$ref) return schema.$ref.split("/").pop()
  if (schema.type === "array" && schema.items) return `${refName(schema.items) ?? schema.items.type ?? "item"}[]`
  if (schema.anyOf || schema.oneOf) return (schema.anyOf ?? schema.oneOf).map(refName).filter((n) => n && n !== "null").join(" | ")
  return schema.type ?? null
}
const bodyOf = (content) => {
  if (!content) return null
  const [type, v] = Object.entries(content)[0] ?? []
  return type ? `${refName(v.schema) ?? "object"} (${type})` : null
}

const byTag = new Map()
for (const [route, item] of Object.entries(spec.paths)) {
  for (const method of METHODS) {
    const op = item[method]
    if (!op) continue
    const tag = op.tags?.[0] ?? "other"
    if (!byTag.has(tag)) byTag.set(tag, [])
    byTag.get(tag).push({ method, route, op, item })
  }
}
const tags = [...byTag.keys()].sort()
const out = (...p) => path.join("reference", "api", ...p)

for (const tag of tags) {
  const ops = byTag.get(tag).sort((a, b) => a.route.localeCompare(b.route) || METHODS.indexOf(a.method) - METHODS.indexOf(b.method))
  const lines = [`# ${tag[0].toUpperCase()}${tag.slice(1)}`, "", `${ops.length} operation${ops.length === 1 ? "" : "s"}. [Back to the API overview](/reference/api/).`, ""]
  for (const { method, route, op, item } of ops) {
    lines.push(`## ${op.summary ?? op.operationId}`, "", `<span class="verb verb-${method}">${method.toUpperCase()}</span> \`${route}\``, "")
    if (op.description) lines.push(cell(op.description).replace(/\\\|/g, "|"), "")
    const params = [...(item.parameters ?? []), ...(op.parameters ?? [])]
    if (params.length) {
      lines.push("| Parameter | In | Type | Required |", "|---|---|---|---|")
      for (const p of params) {
        const t = refName(p.schema) ?? "string"
        const def = p.schema && "default" in p.schema ? ` (default ${JSON.stringify(p.schema.default)})` : ""
        lines.push(`| \`${p.name}\` | ${p.in} | ${cell(t + def)} | ${p.required ? "yes" : "no"} |`)
      }
      lines.push("")
    }
    const req = bodyOf(op.requestBody?.content)
    if (req) lines.push(`**Request body:** \`${req}\`${op.requestBody.required ? "" : " (optional)"}`, "")
    const resp = Object.entries(op.responses ?? {})
      .filter(([code]) => code !== "422")
      .map(([code, r]) => `\`${code}\` ${bodyOf(r.content) ? "`" + bodyOf(r.content) + "`" : cell(r.description ?? "")}`)
    if (resp.length) lines.push(`**Responses:** ${resp.join(" · ")}`, "")
    lines.push(op.security?.length === 0 ? "**Sign-in:** not required" : "**Sign-in:** bearer token (a session or a personal API token)", "")
  }
  writePage(out(`${slug(tag)}.md`), lines.join("\n"), { editPath: SOURCE })
}

const total = tags.reduce((n, t) => n + byTag.get(t).length, 0)
const index = [
  "# API reference",
  "",
  `Verano's HTTP API, generated from the OpenAPI file the web app itself is built on (${total} operations, version ${spec.info.version}). The web app, the command-line tool and the libraries use only this API.`,
  "",
  "- Every route starts with `/api/v1`. Authenticate with `Authorization: Bearer <token>`: a browser session or a personal API token (`verano token create`).",
  "- A running server also serves an interactive version of this reference under `/docs`.",
  `- The raw file: [openapi.json](${REPO_URL}/blob/${BRANCH}/${SOURCE}).`,
  "- Request and response bodies are named here; their fields are in the raw file.",
  "",
  "| Group | Operations |",
  "|---|---:|",
  ...tags.map((t) => `| [${t}](/reference/api/${slug(t)}) | ${byTag.get(t).length} |`),
]
writePage(out("index.md"), index.join("\n"), { editPath: SOURCE })

const generated = path.join(WEBSITE, ".vitepress", "generated")
fs.mkdirSync(generated, { recursive: true })
fs.writeFileSync(
  path.join(generated, "api-sidebar.json"),
  JSON.stringify([{ text: "Overview", link: "/reference/api/" }, ...tags.map((t) => ({ text: t, link: `/reference/api/${slug(t)}` }))], null, 2),
)
console.log(`gen-api: ${total} operations in ${tags.length} groups`)
