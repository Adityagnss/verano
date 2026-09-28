/** The centered card that frames the sign-in and sign-up forms, under the logo and a one-line description of Verano. */
import type { ReactNode } from "react"

import { Logo } from "@/components/common/logo"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

const TAGLINE =
  "Test your prompt on the models you choose, see quality, cost and speed side by side, and get a better prompt proven on unseen cases."

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
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 px-4">
      <div className="flex flex-col items-center gap-2 text-center">
        <Logo size={40} className="[&>span]:text-2xl" />
        <span className="text-text-secondary max-w-sm text-sm">{TAGLINE}</span>
      </div>
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-lg">{title}</CardTitle>
          <CardDescription>{subtitle}</CardDescription>
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    </main>
  )
}
