/**
 * Number, money and size formatting used across screens. Prices arrive from the API as
 * decimal strings per million tokens; an unknown price is null and is shown as such, never
 * as $0 (DEVELOPMENT.md 1.3).
 */
const USD = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 4 })
const COUNT = new Intl.NumberFormat("en-US")
const COMPACT = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 })

export function formatCost(value: string | number | null | undefined): string {
  const amount = Number(value ?? 0)
  return amount > 0 && amount < 0.0001 ? "< $0.0001" : USD.format(amount)
}

export function formatMs(value: number): string {
  return value < 1 ? "< 1 ms" : value < 1000 ? `${Math.round(value)} ms` : `${(value / 1000).toFixed(1)} s`
}

export function formatCount(value: number): string {
  return COUNT.format(value)
}

export function formatTokens(value: number | null | undefined): string {
  return value ? COMPACT.format(value) : "—"
}

export function formatPricePair(input: string | null, output: string | null): string {
  return `${USD.format(Number(input))} / ${USD.format(Number(output))}`
}

/** A prompt version's short name: v3 for a saved version, "Improve candidate 1" for one Improve is testing. */
export function versionName(version: number): string {
  return version < 0 ? `Improve candidate ${-version}` : `v${version}`
}
