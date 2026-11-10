/**
 * The frame around every project page: the responsive app frame with the project's navigation.
 * The navigation comes from `src/lib/nav.ts`, grouped (Set up, Test, Improve, Trust, Production,
 * Help). Pages on the guided path show whether they are done, the current page is highlighted,
 * and the first unfinished one is marked "Next". The project name and the running model cost stay
 * visible (sidebar and header pill). When some calls used models with an unknown price, the cost
 * says so instead of looking complete.
 */
"use client"

import { Check } from "lucide-react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import type { ReactNode } from "react"

import { COMMON_COPY } from "@/components/common/copy"
import {
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { formatCost } from "@/lib/format"
import { ACCOUNT_NAV, itemsOf, NAV_GROUPS, type NavItem, projectHref, TRENDS_NAV } from "@/lib/nav"
import { type StepKey } from "@/lib/steps"
import { cn } from "@/lib/utils"

import { useCostSummary, useProject, useStepCompletion } from "../hooks"
import { AppFrame } from "./app-frame"
import { SpendPill } from "./spend-pill"

type Done = Partial<Record<StepKey, boolean>>

/** The first available guided page that is not done yet. */
export function firstOpenKey(items: NavItem[], done: Done): string | undefined {
  return items.find((item) => item.guided && item.available && !done[item.key as StepKey])?.key
}

function NavLink({
  projectId,
  item,
  pathname,
  done,
  next,
}: {
  projectId: string
  item: NavItem
  pathname: string
  done: Done
  next: boolean
}) {
  const href = projectHref(projectId, item)
  const active = pathname.startsWith(href)
  const finished = item.guided && done[item.key as StepKey]
  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        isActive={active}
        tooltip={item.label}
        aria-current={active ? "page" : undefined}
        aria-disabled={!item.available || undefined}
        title={item.subtitle}
        render={<Link href={href} />}
      >
        <item.icon aria-hidden className={cn(active && "text-lagoon-strong")} />
        <span>{item.label}</span>
        {finished ? (
          <>
            <Check aria-hidden className="text-success-strong ml-auto" strokeWidth={3} />
            <span className="sr-only">(done)</span>
          </>
        ) : next && !active ? (
          <span className="bg-lagoon-soft text-lagoon-strong ml-auto rounded-full px-2 py-0.5 text-[11px] font-semibold group-data-[collapsible=icon]:hidden">
            Next
          </span>
        ) : null}
      </SidebarMenuButton>
    </SidebarMenuItem>
  )
}

function ProjectSidebarBody({ projectId, pathname }: { projectId: string; pathname: string }) {
  const done: Done = useStepCompletion(projectId).data ?? {}
  const project = useProject(projectId).data
  const cost = useCostSummary(projectId).data
  const guided = NAV_GROUPS.flatMap((group) => itemsOf(group.id)).filter((item) => item.guided)
  const doneCount = guided.filter((item) => done[item.key as StepKey]).length
  const next = firstOpenKey(guided, done)
  return (
    <>
      <SidebarContent>
        <div className="px-4 pt-3 pb-1 group-data-[collapsible=icon]:hidden">
          <p className="truncate text-sm font-semibold" title={project?.name}>
            {project?.name ?? COMMON_COPY.loading}
          </p>
          <p className="text-text-secondary text-xs">
            {COMMON_COPY.stepsDone(doneCount, guided.length)} · {formatCost(cost?.cost)} spent
          </p>
        </div>
        {NAV_GROUPS.map((group) => (
          <SidebarGroup key={group.id}>
            <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
            <SidebarMenu>
              {itemsOf(group.id).map((item) => (
                <NavLink
                  key={item.key}
                  projectId={projectId}
                  item={item}
                  pathname={pathname}
                  done={done}
                  next={item.key === next}
                />
              ))}
            </SidebarMenu>
          </SidebarGroup>
        ))}
      </SidebarContent>
      <SidebarFooter className="border-t">
        <SidebarMenu>
          <NavLink projectId={projectId} item={TRENDS_NAV} pathname={pathname} done={done} next={false} />
          <SidebarMenuItem>
            <SidebarMenuButton tooltip={ACCOUNT_NAV[0].label} render={<Link href={ACCOUNT_NAV[0].href} />}>
              {(() => {
                const Icon = ACCOUNT_NAV[0].icon
                return <Icon aria-hidden />
              })()}
              <span>{ACCOUNT_NAV[0].label}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </>
  )
}

export function ProjectShell({ projectId, children }: { projectId: string; children: ReactNode }) {
  const pathname = usePathname()
  const project = useProject(projectId).data
  const segment = /^\/projects\/[^/]+\/([^/]+)/.exec(pathname)?.[1]
  const page = [...itemsOf("setup"), ...NAV_GROUPS.flatMap((g) => itemsOf(g.id)), TRENDS_NAV].find(
    (item) => item.segment === segment,
  )
  return (
    <AppFrame
      sidebar={<ProjectSidebarBody projectId={projectId} pathname={pathname} />}
      crumbs={[
        { label: COMMON_COPY.projects, href: "/projects" },
        { label: project?.name ?? COMMON_COPY.loading, href: projectHref(projectId, "keys") },
        ...(page ? [{ label: page.label }] : []),
      ]}
      spend={<SpendPill projectId={projectId} />}
    >
      {children}
    </AppFrame>
  )
}
