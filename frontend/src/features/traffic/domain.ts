/** Small pure helpers for the traffic screens. */
import type { DailyScore } from "./types"

export function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? "–" : `${Math.round(value * 100)}%`
}

export type Series = { label: string; points: { day: string; rate: number | null }[] }

/** One line per prompt version, plus one for all versions together, each with a point per day. */
export function seriesOf(rows: DailyScore[], allLabel: string, noVersion: string): Series[] {
  const days = [...new Set(rows.map((r) => r.day))].sort()
  const versions = [...new Set(rows.map((r) => r.prompt_version ?? ""))].sort()
  const all: Series = {
    label: allLabel,
    points: days.map((day) => {
      const of = rows.filter((r) => r.day === day)
      const scored = of.reduce((n, r) => n + r.scored, 0)
      const passed = of.reduce((n, r) => n + r.passed, 0)
      return { day, rate: scored ? passed / scored : null }
    }),
  }
  if (versions.length <= 1) return [all]
  const each = versions.map((version) => ({
    label: version || noVersion,
    points: days.map((day) => {
      const row = rows.find((r) => r.day === day && (r.prompt_version ?? "") === version)
      return { day, rate: row?.pass_rate ?? null }
    }),
  }))
  return [all, ...each]
}

export function linePath(points: { rate: number | null }[], width: number, height: number): string {
  const step = points.length > 1 ? width / (points.length - 1) : 0
  let path = ""
  let pen = false
  points.forEach((p, i) => {
    if (p.rate === null) {
      pen = false
      return
    }
    path += `${pen ? "L" : "M"}${(i * step).toFixed(1)} ${((1 - p.rate) * height).toFixed(1)} `
    pen = true
  })
  return path.trim()
}
