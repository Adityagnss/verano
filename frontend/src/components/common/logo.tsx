/** Verano's mark: a marigold sun over a lagoon-teal horizon (verano: summer), and the wordmark. */
import { cn } from "@/lib/utils"

import { COMMON_COPY } from "./copy"

export function Logo({ size = 26, className }: { size?: number; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
        <circle cx="16" cy="14" r="8" fill="var(--marigold)" />
        <path
          d="M3 22.5c3.2 0 3.2-2 6.5-2s3.3 2 6.5 2 3.3-2 6.5-2 3.3 2 6.5 2"
          fill="none"
          stroke="var(--lagoon)"
          strokeWidth="2.6"
          strokeLinecap="round"
        />
        <path
          d="M6 27c2.5 0 2.5-1.6 5-1.6s2.5 1.6 5 1.6 2.5-1.6 5-1.6 2.5 1.6 5 1.6"
          fill="none"
          stroke="var(--lagoon)"
          strokeOpacity="0.45"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
      <span className="text-[1.15rem] font-semibold tracking-tight [font-stretch:87.5%]">
        {COMMON_COPY.appName}
      </span>
    </span>
  )
}
