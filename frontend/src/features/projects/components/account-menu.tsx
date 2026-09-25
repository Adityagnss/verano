/** Shows who is signed in, with a sign-out button that ends the server session too. */
"use client"

import { LogOut } from "lucide-react"
import { useRouter } from "next/navigation"

import { COMMON_COPY } from "@/components/common/copy"
import { Button } from "@/components/ui/button"
import { useSession } from "@/lib/auth/use-session"

import { useSignOutAndLeave } from "../use-sign-out"

export function AccountMenu() {
  const { user } = useSession()
  const router = useRouter()
  const signOut = useSignOutAndLeave(() => router.replace("/login"))
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="text-muted-foreground">{user?.email}</span>
      <Button variant="ghost" size="sm" onClick={() => signOut.mutate()} disabled={signOut.isPending}>
        <LogOut />
        {COMMON_COPY.signOut}
      </Button>
    </div>
  )
}
