/**
 * Root layout: fonts and providers. Instrument Sans (text) and JetBrains Mono (prompts and outputs)
 * are self-hosted from npm packages, so neither the build nor the browser contacts a font
 * service, and the build works offline.
 */
import "@fontsource-variable/instrument-sans/standard.css"
import "@fontsource-variable/jetbrains-mono"
import "./globals.css"

import type { Metadata } from "next"
import type { ReactNode } from "react"

import { AppProviders } from "@/components/common/app-providers"

export const metadata: Metadata = {
  title: "Verano",
  description: "LLM experimentation and prompt optimization studio",
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="font-sans">
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  )
}
