/**
 * Number, money and size formatting used across screens. Prices arrive from the API as
 * decimal strings per million tokens; an unknown price is null and is shown as such, never
 * as $0 (DEVELOPMENT.md 1.3).
 */
const USD = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 4 })
const COUNT = new Intl.NumberFormat("en-US")
const COMPACT = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 })

export function formatCost(value: string | number | null | undefined): string {
  return USD.format(Number(value ?? 0))
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
