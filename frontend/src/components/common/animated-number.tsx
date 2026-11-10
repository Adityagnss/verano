/**
 * A number that counts up to its value (Magic UI NumberTicker) when it first appears. Under
 * reduced motion, or when `animate` is false, it is plain text. Use it for the few numbers that
 * matter (a score, a total), not for every figure in a table. Pass `format` for money or units;
 * a formatter makes it plain text too, since the ticker only knows plain numbers.
 *
 *   <AnimatedNumber value={42} />
 *   <AnimatedNumber value={0.8} decimals={1} suffix="%" />
 */
"use client"

import { useReducedMotion } from "motion/react"

import { NumberTicker } from "@/components/ui/number-ticker"
import { cn } from "@/lib/utils"

export function AnimatedNumber({
  value,
  decimals = 0,
  prefix = "",
  suffix = "",
  format,
  animate = true,
  className,
}: {
  value: number
  decimals?: number
  prefix?: string
  suffix?: string
  /** Custom text for the value; disables the count-up. */
  format?: (value: number) => string
  animate?: boolean
  className?: string
}) {
  const reduced = useReducedMotion()
  const plain = format
    ? format(value)
    : `${prefix}${value.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}${suffix}`
  if (reduced || !animate || format) {
    return <span className={cn("tabular-nums", className)}>{plain}</span>
  }
  return (
    <span className={cn("tabular-nums", className)}>
      {prefix}
      <NumberTicker value={value} decimalPlaces={decimals} className="text-inherit" />
      {suffix}
    </span>
  )
}
