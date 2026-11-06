/** Shows who is signed in, with a sign-out button that ends the server session too. */
"use client"

import { LogOut } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"

import { COMMON_COPY } from "@/components/common/copy"
import { ThemeSwitch } from "@/components/common/theme-switch"
import { Button } from "@/components/ui/button"
import { useSession } from "@/lib/auth/use-session"

import { useSignOutAndLeave } from "../use-sign-out"

export function AccountMenu() {
  const { user } = useSession()
  const router = useRouter()
  const signOut = useSignOutAndLeave(() => router.replace("/login"))
  return (
    <div className="flex items-center gap-3 text-sm">
      <ThemeSwitch />
      <span className="text-muted-foreground hidden max-w-[16rem] truncate lg:inline">{user?.email}</span>
      <Link href="/workspace" className="text-text-secondary hover:text-foreground">
        Workspace
      </Link>
      <Button
        variant="ghost"
        size="sm"
        aria-label={COMMON_COPY.signOut}
        onClick={() => signOut.mutate()}
        disabled={signOut.isPending}
      >
        <LogOut />
        <span className="hidden sm:inline">{COMMON_COPY.signOut}</span>
      </Button>
    </div>
  )
}
