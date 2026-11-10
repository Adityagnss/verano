// A tiny layout engine for the site's diagrams. A diagram is a list of layers; each layer is a few nodes.
// "rows" puts layers top to bottom. "h" puts layers left to right on wide screens and top to bottom on phones.
export type Kind = "plain" | "edge" | "core" | "ok" | "warn" | "muted"
export interface NodeSpec {
  id: string
  label: string
  sub?: string
  kind?: Kind
}
export interface EdgeSpec {
  from: string
  to: string
  label?: string
  both?: boolean
}
export interface DiagramSpec {
  alt: string
  flow: "rows" | "h"
  layers: NodeSpec[][]
  edges: EdgeSpec[]
}
export interface PlacedNode extends NodeSpec {
  x: number
  y: number
  w: number
  h: number
  lines: string[]
  subLines: string[]
}
export interface PlacedEdge {
  d: string
  label?: string
  lx: number
  ly: number
  both: boolean
}
export interface Layout {
  width: number
  height: number
  nodes: PlacedNode[]
  edges: PlacedEdge[]
}

const LABEL_PX = 7.6
const SUB_PX = 6.4

function wrap(text: string, maxPx: number, px: number): string[] {
  const maxChars = Math.max(6, Math.floor(maxPx / px))
  const out: string[] = []
  let cur = ""
  for (const word of text.split(" ")) {
    if (cur && (cur + " " + word).length > maxChars) {
      out.push(cur)
      cur = word
    } else cur = cur ? cur + " " + word : word
  }
  if (cur) out.push(cur)
  return out
}

function place(n: NodeSpec, w: number, showSub: boolean): PlacedNode {
  const lines = wrap(n.label, w - 20, LABEL_PX)
  const subLines = showSub && n.sub ? wrap(n.sub, w - 20, SUB_PX) : []
  const h = 24 + lines.length * 18 + (subLines.length ? subLines.length * 15 + 4 : 0)
  return { ...n, x: 0, y: 0, w, h: Math.max(h, 52), lines, subLines }
}

export function layout(spec: DiagramSpec, wide: boolean): Layout {
  const horizontal = spec.flow === "h" && wide
  const pad = 8
  const W = wide ? (spec.flow === "rows" ? 700 : 960) : 360
  const layers: PlacedNode[][] = []

  if (horizontal) {
    const gap = 44
    const cw = (W - pad * 2 - (spec.layers.length - 1) * gap) / spec.layers.length
    const showSub = cw >= 150
    spec.layers.forEach((layer) => layers.push(layer.map((n) => place(n, cw, showSub))))
    const colH = layers.map((l) => l.reduce((s, n) => s + n.h, 0) + (l.length - 1) * 16)
    const H = Math.max(...colH)
    layers.forEach((l, i) => {
      let y = pad + (H - colH[i]) / 2
      l.forEach((n) => {
        n.x = pad + i * (cw + gap)
        n.y = y
        y += n.h + 16
      })
    })
    return finish(spec, layers, W, H + pad * 2, true)
  }

  const gapX = wide ? 28 : 12
  const gapY = wide ? 48 : 36
  let y = pad
  spec.layers.forEach((layer) => {
    const n = layer.length
    const cap = wide ? 230 : 400
    const w = Math.min(cap, (W - pad * 2 - (n - 1) * gapX) / n)
    const placed = layer.map((x) => place(x, w, true))
    const rowH = Math.max(...placed.map((p) => p.h))
    const total = n * w + (n - 1) * gapX
    let x = (W - total) / 2
    placed.forEach((p) => {
      p.x = x
      p.y = y + (rowH - p.h) / 2
      x += w + gapX
    })
    layers.push(placed)
    y += rowH + gapY
  })
  return finish(spec, layers, W, y - gapY + pad, false)
}

function finish(spec: DiagramSpec, layers: PlacedNode[][], width: number, height: number, horizontal: boolean): Layout {
  const nodes: PlacedNode[] = layers.flat()
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const layerOf = new Map<string, number>()
  layers.forEach((l, i) => l.forEach((n) => layerOf.set(n.id, i)))
  const edges: PlacedEdge[] = spec.edges.map((e) => {
    const a = byId.get(e.from)!
    const b = byId.get(e.to)!
    const down = (layerOf.get(e.to) ?? 0) >= (layerOf.get(e.from) ?? 0)
    let d: string
    let ox: number, oy: number, ix: number, iy: number
    if (horizontal) {
      ox = down ? a.x + a.w : a.x
      oy = a.y + a.h / 2
      ix = down ? b.x : b.x + b.w
      iy = b.y + b.h / 2
      const k = Math.abs(ix - ox) / 2
      d = `M${ox} ${oy} C${ox + (down ? k : -k)} ${oy} ${ix - (down ? k : -k)} ${iy} ${ix} ${iy}`
    } else {
      ox = a.x + a.w / 2
      ix = b.x + b.w / 2
      oy = down ? a.y + a.h : a.y
      iy = down ? b.y : b.y + b.h
      const k = Math.abs(iy - oy) / 2
      d = `M${ox} ${oy} C${ox} ${oy + (down ? k : -k)} ${ix} ${iy - (down ? k : -k)} ${ix} ${iy}`
    }
    return { d, label: e.label, lx: (ox + ix) / 2, ly: (oy + iy) / 2, both: !!e.both }
  })
  return { width, height, nodes, edges }
}
