/**
 * A small colored label for a state or a kind (DEVELOPMENT.md C1: status is never color
 * alone, so every badge carries a word, and status tones may add an icon). Tones map to the
 * soft/strong token pairs: neutral, brand (lagoon), success, warning, danger, info, violet, gold.
 */
import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

export type Tone = "neutral" | "brand" | "success" | "warning" | "danger" | "info" | "violet" | "gold"

const TONES: Record<Tone, string> = {
  neutral: "bg-subtle text-text-secondary ring-border",
  brand: "bg-brand-soft text-brand-strong ring-brand-strong/15",
  success: "bg-success-soft text-success-strong ring-success/20",
  warning: "bg-warning-soft text-warning-strong ring-warning/25",
  danger: "bg-danger-soft text-danger-strong ring-danger/20",
  info: "bg-info-soft text-info-strong ring-info-strong/15",
  violet: "bg-violet-soft text-violet-strong ring-violet-strong/15",
  gold: "bg-gold-soft text-gold-strong ring-gold-strong/20",
}

export function StatusBadge({
  tone = "neutral",
  icon,
  children,
  className,
}: {
  tone?: Tone
  icon?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <span
      className={cn(
        "inline-flex h-5 shrink-0 items-center gap-1 rounded-full px-2 text-xs font-medium whitespace-nowrap ring-1 ring-inset [&>svg]:size-3",
        TONES[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  )
}
