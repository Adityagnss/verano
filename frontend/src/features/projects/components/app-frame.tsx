/**
 * The responsive frame shared by every signed-in screen (project pages and the pages outside a
 * project). Built on the shadcn Sidebar:
 *   1280px and wider: full sidebar
 *   1024 to 1279px:   icon rail (the menu button expands it)
 *   below 1024px:     a drawer (Sheet) opened by the menu button
 * The slim header holds: menu button, breadcrumb, spend pill, search (Cmd/Ctrl+K), theme and
 * ONE account menu. Pass the sidebar body as `sidebar`, the crumbs as `crumbs`, and the spend
 * pill as `spend`.
 */
"use client"

import { Search } from "lucide-react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { type ReactNode, useEffect, useSyncExternalStore } from "react"

import { CommandPalette, openCommandPalette } from "@/components/common/command-palette"
import { Logo } from "@/components/common/logo"
import { ThemeSwitch } from "@/components/common/theme-switch"
import { useBreakpoint } from "@/components/common/use-breakpoint"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { Button } from "@/components/ui/button"
import { Kbd } from "@/components/ui/kbd"
import {
  Sidebar,
  SidebarHeader,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar"
import { TooltipProvider } from "@/components/ui/tooltip"

import { AccountMenu } from "./account-menu"

export type Crumb = { label: string; href?: string }

const noopSubscribe = () => () => undefined

function useIsMac(): boolean {
  return useSyncExternalStore(
    noopSubscribe,
    () => /Mac|iPhone|iPad/.test(navigator.platform),
    () => false,
  )
}

function SearchButton() {
  const mac = useIsMac()
  return (
    <Button
      variant="outline"
      aria-label="Search pages and projects"
      onClick={openCommandPalette}
      className="h-10 min-w-10 justify-start gap-2 px-0 sm:px-3 md:w-44 lg:w-52"
    >
      <Search aria-hidden className="mx-auto sm:mx-0" />
      <span className="text-muted-foreground hidden flex-1 text-left font-normal md:inline">Search…</span>
      <Kbd className="hidden lg:inline-flex">{mac ? "⌘K" : "Ctrl K"}</Kbd>
    </Button>
  )
}

function Crumbs({ crumbs }: { crumbs: Crumb[] }) {
  return (
    <Breadcrumb className="min-w-0 flex-1">
      <BreadcrumbList className="flex-nowrap">
        {crumbs.map((crumb, index) => {
          const last = index === crumbs.length - 1
          return (
            <BreadcrumbItem
              key={`${crumb.label}-${index}`}
              className={last ? "min-w-0" : "hidden min-w-0 sm:inline-flex"}
            >
              {last || !crumb.href ? (
                <BreadcrumbPage className="block max-w-[14rem] truncate sm:max-w-xs lg:max-w-md">
                  {crumb.label}
                </BreadcrumbPage>
              ) : (
                <BreadcrumbLink render={<Link href={crumb.href} />} className="block max-w-[10rem] truncate">
                  {crumb.label}
                </BreadcrumbLink>
              )}
              {last ? null : <BreadcrumbSeparator className="hidden sm:block" />}
            </BreadcrumbItem>
          )
        })}
      </BreadcrumbList>
    </Breadcrumb>
  )
}

function Frame({
  sidebar,
  crumbs,
  spend,
  children,
}: {
  sidebar: ReactNode
  crumbs: Crumb[]
  spend?: ReactNode
  children: ReactNode
}) {
  const pathname = usePathname()
  const { setOpenMobile, setOpen } = useSidebar()
  const wide = useBreakpoint().atLeast("xl")
  // The drawer closes after you pick a page.
  useEffect(() => setOpenMobile(false), [pathname, setOpenMobile])
  // Full sidebar from 1280px, icon rail below that; the menu button still toggles it by hand.
  // `setOpen` changes whenever the sidebar toggles, so it must not be a dependency here.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => setOpen(wide), [wide])
  return (
    <>
      <Sidebar collapsible="icon">
        <SidebarHeader className="h-14 justify-center border-b px-3">
          <Link
            href="/projects"
            aria-label="Verano, all projects"
            className="inline-flex min-h-10 items-center"
          >
            <Logo size={28} className="group-data-[collapsible=icon]:[&>span]:sr-only" />
          </Link>
        </SidebarHeader>
        {sidebar}
        <SidebarRail />
      </Sidebar>
      <div className="flex min-w-0 flex-1 flex-col">
        <a
          href="#main"
          className="bg-card focus:ring-ring sr-only z-50 rounded-md px-3 py-2 text-sm focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:ring-2"
        >
          Skip to content
        </a>
        <header
          data-slot="app-header"
          className="border-border bg-background/85 sticky top-0 z-20 flex h-14 shrink-0 items-center gap-1.5 border-b px-2 backdrop-blur sm:gap-2 sm:px-4"
        >
          <SidebarTrigger className="size-10" aria-label="Open menu" />
          <Crumbs crumbs={crumbs} />
          <div className="flex shrink-0 items-center gap-0.5 sm:gap-1.5">
            {spend}
            <SearchButton />
            <ThemeSwitch />
            <AccountMenu />
          </div>
        </header>
        <main id="main" className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
          {children}
        </main>
      </div>
      <CommandPalette />
    </>
  )
}

export function AppFrame(props: {
  sidebar: ReactNode
  crumbs: Crumb[]
  spend?: ReactNode
  children: ReactNode
}) {
  return (
    <TooltipProvider delay={300}>
      <SidebarProvider defaultOpen={false} className="min-h-svh">
        <Frame {...props} />
      </SidebarProvider>
    </TooltipProvider>
  )
}
