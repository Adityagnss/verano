/**
 * The one account dropdown in the header: who is signed in (email), then Usage and spend,
 * Workspace, API tokens and Sign out (which also ends the server session).
 */
"use client"

import { ChevronDown, LogOut, UserRound } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"

import { COMMON_COPY } from "@/components/common/copy"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useSession } from "@/lib/auth/use-session"
import { ACCOUNT_NAV } from "@/lib/nav"

import { useSignOutAndLeave } from "../use-sign-out"

export function AccountMenu() {
  const { user } = useSession()
  const router = useRouter()
  const signOut = useSignOutAndLeave(() => router.replace("/login"))
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button variant="ghost" aria-label="Account menu" className="h-10 gap-1 px-2 sm:px-2.5">
            <UserRound aria-hidden />
            <ChevronDown aria-hidden className="size-3.5" />
          </Button>
        }
      />
      <DropdownMenuContent align="end" className="w-64 min-w-64">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="truncate py-2" data-testid="account-email">
            {user?.email ?? "Signed in"}
          </DropdownMenuLabel>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        {ACCOUNT_NAV.map((page) => (
          <DropdownMenuItem key={page.key} className="min-h-10" render={<Link href={page.href} />}>
            <page.icon aria-hidden />
            {page.label}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem className="min-h-10" disabled={signOut.isPending} onClick={() => signOut.mutate()}>
          <LogOut aria-hidden />
          {COMMON_COPY.signOut}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
