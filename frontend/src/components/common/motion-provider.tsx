/**
 * Wraps the app in motion's `MotionConfig` with `reducedMotion="user"`: when the person's system
 * asks for reduced motion, every `motion.*` element skips transform and layout animation.
 * Mounted once in AppProviders; feature code never needs to add it again.
 */
"use client"

import { MotionConfig } from "motion/react"
import type { ReactNode } from "react"

export function MotionProvider({ children }: { children: ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>
}
