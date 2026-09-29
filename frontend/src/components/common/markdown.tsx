/**
 * A small, safe renderer for the notes written in Markdown (headings, paragraphs, bullet and
 * numbered lists, quotes, **bold**, *italic*, `code` and [links](https://…)). Nothing is
 * inserted as HTML, so a note can never run script. Level-2 headings get an `id` so a
 * table of contents can link to them.
 */
import type { ReactNode } from "react"

export type NoteHeading = { id: string; title: string }

const INLINE = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)\s]+\))/g

export function slug(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
}

export function headingsOf(markdown: string): NoteHeading[] {
  return markdown
    .split("\n")
    .filter((line) => line.startsWith("## "))
    .map((line) => ({ id: slug(line.slice(3)), title: line.slice(3).trim() }))
}

function inline(text: string): ReactNode[] {
  return text.split(INLINE).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>
    if (part.startsWith("`") && part.endsWith("`"))
      return (
        <code key={index} className="bg-subtle rounded px-1 py-0.5 text-[0.85em]">
          {part.slice(1, -1)}
        </code>
      )
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2)
      return <em key={index}>{part.slice(1, -1)}</em>
    const link = /^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/.exec(part)
    if (link)
      return (
        <a
          key={index}
          href={link[2]}
          target="_blank"
          rel="noreferrer"
          className="text-lagoon-strong underline"
        >
          {link[1]}
        </a>
      )
    return part
  })
}

type Block =
  { kind: "h1" | "h2" | "h3" | "p" | "quote"; text: string } | { kind: "ul" | "ol"; items: string[] }

function blocks(markdown: string): Block[] {
  const out: Block[] = []
  let paragraph: string[] = []
  const flush = () => {
    if (paragraph.length) out.push({ kind: "p", text: paragraph.join(" ") })
    paragraph = []
  }
  for (const raw of markdown.split("\n")) {
    const line = raw.trimEnd()
    const bullet = /^\s*[-*]\s+(.*)$/.exec(line)
    const numbered = /^\s*\d+\.\s+(.*)$/.exec(line)
    const heading = /^(#{1,3}) (.*)$/.exec(line)
    if (!line.trim()) {
      flush()
    } else if (heading) {
      flush()
      out.push({ kind: (["h1", "h2", "h3"] as const)[heading[1].length - 1], text: heading[2] })
    } else if (line.startsWith("> ")) {
      flush()
      out.push({ kind: "quote", text: line.slice(2) })
    } else if (bullet || numbered) {
      flush()
      const kind = bullet ? "ul" : "ol"
      const last = out[out.length - 1]
      const text = (bullet ?? numbered)![1]
      if (last && last.kind === kind) last.items.push(text)
      else out.push({ kind, items: [text] })
    } else paragraph.push(line.trim())
  }
  flush()
  return out
}

export function Markdown({ source }: { source: string }) {
  return (
    <div className="flex flex-col gap-3 text-[0.9375rem] leading-relaxed">
      {blocks(source).map((block, index) => {
        switch (block.kind) {
          case "h1":
            return (
              <h3 key={index} className="text-xl font-semibold">
                {inline(block.text)}
              </h3>
            )
          case "h2":
            return (
              <h3
                key={index}
                id={slug(block.text)}
                className="border-border mt-4 scroll-mt-24 border-t pt-5 text-lg font-semibold"
              >
                {inline(block.text)}
              </h3>
            )
          case "h3":
            return (
              <h4 key={index} className="mt-2 font-semibold">
                {inline(block.text)}
              </h4>
            )
          case "quote":
            return (
              <blockquote key={index} className="border-lagoon text-text-secondary border-l-2 pl-3">
                {inline(block.text)}
              </blockquote>
            )
          case "ul":
            return (
              <ul key={index} className="marker:text-lagoon flex list-disc flex-col gap-1.5 pl-5">
                {block.items.map((item, i) => (
                  <li key={i}>{inline(item)}</li>
                ))}
              </ul>
            )
          case "ol":
            return (
              <ol key={index} className="marker:text-lagoon flex list-decimal flex-col gap-1.5 pl-5">
                {block.items.map((item, i) => (
                  <li key={i}>{inline(item)}</li>
                ))}
              </ol>
            )
          default:
            return (
              <p key={index} className="text-text-secondary">
                {inline(block.text)}
              </p>
            )
        }
      })}
    </div>
  )
}
