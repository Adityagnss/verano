/**
 * The frame for pages outside a project (/projects, /workspace, /tokens, /activity): the same
 * responsive sidebar and slim header as the project shell, with the account pages and the user's
 * latest projects in the sidebar. Wrap a page (or a layout) with it.
 *
 *   <AccountFrame>{page}</AccountFrame>
 */
"use client"

import { FolderKanban } from "lucide-react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import type { ReactNode } from "react"

import {
  SidebarContent,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { ACCOUNT_NAV, accountPageForPath, PROJECTS_NAV } from "@/lib/nav"

import { useProjects } from "../hooks"
import { AppFrame } from "./app-frame"
import { SpendPill } from "./spend-pill"

const RECENT = 6

function AccountSidebarBody({ pathname }: { pathname: string }) {
  const projects = useProjects().data?.items.slice(0, RECENT) ?? []
  return (
    <SidebarContent>
      <SidebarGroup>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              isActive={pathname === PROJECTS_NAV.href}
              tooltip={PROJECTS_NAV.label}
              aria-current={pathname === PROJECTS_NAV.href ? "page" : undefined}
              render={<Link href={PROJECTS_NAV.href} />}
            >
              <PROJECTS_NAV.icon aria-hidden />
              <span>{PROJECTS_NAV.label}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarGroup>
      {projects.length ? (
        <SidebarGroup>
          <SidebarGroupLabel>Recent projects</SidebarGroupLabel>
          <SidebarMenu>
            {projects.map((project) => (
              <SidebarMenuItem key={project.id}>
                <SidebarMenuButton
                  tooltip={project.name}
                  render={<Link href={`/projects/${project.id}/keys`} />}
                >
                  <FolderKanban aria-hidden />
                  <span>{project.name}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroup>
      ) : null}
      <SidebarGroup>
        <SidebarGroupLabel>Account</SidebarGroupLabel>
        <SidebarMenu>
          {ACCOUNT_NAV.map((page) => {
            const active = pathname === page.href || pathname.startsWith(`${page.href}/`)
            return (
              <SidebarMenuItem key={page.key}>
                <SidebarMenuButton
                  isActive={active}
                  tooltip={page.label}
                  aria-current={active ? "page" : undefined}
                  title={page.subtitle}
                  render={<Link href={page.href} />}
                >
                  <page.icon aria-hidden />
                  <span>{page.label}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            )
          })}
        </SidebarMenu>
      </SidebarGroup>
    </SidebarContent>
  )
}

export function AccountFrame({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const page = accountPageForPath(pathname)
  return (
    <AppFrame
      sidebar={<AccountSidebarBody pathname={pathname} />}
      crumbs={[
        { label: PROJECTS_NAV.label, href: page ? PROJECTS_NAV.href : undefined },
        ...(page ? [{ label: page.label }] : []),
      ]}
      spend={<SpendPill />}
    >
      {children}
    </AppFrame>
  )
}
