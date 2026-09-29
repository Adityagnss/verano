/** Verano's mark: a blue tile holding a "V" whose right stroke closes into a loop arrow (test, improve, repeat), and the wordmark. */
import { useId } from "react"

import { cn } from "@/lib/utils"

import { COMMON_COPY } from "./copy"

export function Logo({ size = 28, className }: { size?: number; className?: string }) {
  const gradient = `verano-mark-${useId().replace(/:/g, "")}`
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
        <defs>
          <linearGradient id={gradient} x1="4" y1="2" x2="28" y2="30" gradientUnits="userSpaceOnUse">
            <stop stopColor="#3b82f6" />
            <stop offset="1" stopColor="#1d4ed8" />
          </linearGradient>
        </defs>
        <rect width="32" height="32" rx="9" fill={`url(#${gradient})`} />
        <path
          d="M8.5 10.5 14.2 22a1.9 1.9 0 0 0 3.4 0l5.2-10.4"
          fill="none"
          stroke="#fff"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="23.2" cy="8.6" r="2.4" fill="#93c5fd" />
      </svg>
      <span className="text-[1.15rem] font-semibold tracking-tight [font-stretch:87.5%]">
        {COMMON_COPY.appName}
      </span>
    </span>
  )
}
