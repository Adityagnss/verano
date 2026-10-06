/**
 * The frame around the sign-in and sign-up forms: on wide screens a blue brand panel that
 * says what Verano does, beside the form; on narrow screens just the logo, a line about
 * Verano, and the form.
 */
import { BarChart3, Repeat2, Target } from "lucide-react"
import type { ReactNode } from "react"

import { Logo } from "@/components/common/logo"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

const TAGLINE =
  "Test your prompt on the models you choose, see quality, cost and speed side by side, and get better prompts, called better only when proven on unseen cases."

const POINTS = [
  {
    icon: BarChart3,
    title: "Compare models side by side",
    text: "Quality, cost and speed for the same prompt.",
  },
  {
    icon: Target,
    title: "Score against your own answers",
    text: "Upload your files and golden answers; every model is checked the same way.",
  },
  {
    icon: Repeat2,
    title: "Improve with proof",
    text: "New prompt versions are tested on cases they were never written from.",
  },
]

export function AuthCard({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle: string
  children: ReactNode
}) {
  return (
    <main className="grid min-h-screen lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
      <aside className="relative hidden flex-col justify-between overflow-hidden bg-gradient-to-br from-[#1e40af] via-[#1d4ed8] to-[#3b82f6] p-12 text-white lg:flex">
        <div
          aria-hidden
          className="pointer-events-none absolute -top-24 -right-24 size-96 rounded-full bg-white/10 blur-2xl"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-32 -left-16 size-96 rounded-full bg-sky-300/20 blur-3xl"
        />
        <Logo size={40} tone="light" className="relative [&>span]:text-2xl" />
        <div className="relative flex max-w-lg flex-col gap-8">
          <h2 className="text-4xl leading-tight font-semibold [font-stretch:87.5%]">
            Know which prompt and which model really works.
          </h2>
          <ul className="flex flex-col gap-5">
            {POINTS.map((point) => (
              <li key={point.title} className="flex gap-4">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-white/15 ring-1 ring-white/25">
                  <point.icon className="size-5" />
                </span>
                <span className="flex flex-col">
                  <span className="font-semibold">{point.title}</span>
                  <span className="text-sm text-white/75">{point.text}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-sm text-white/60">Measure first. Change one thing at a time.</p>
      </aside>
      <div className="flex flex-col items-center justify-center gap-6 px-4 py-10">
        <div className="flex flex-col items-center gap-2 text-center lg:hidden">
          <Logo size={40} className="[&>span]:text-2xl" />
          <span className="text-text-secondary max-w-sm text-sm">{TAGLINE}</span>
        </div>
        <Card className="w-full max-w-sm shadow-[0_8px_30px_rgb(20_32_58/0.08)]">
          <CardHeader>
            <CardTitle className="text-lg">{title}</CardTitle>
            <CardDescription>{subtitle}</CardDescription>
          </CardHeader>
          <CardContent>{children}</CardContent>
        </Card>
      </div>
    </main>
  )
}
