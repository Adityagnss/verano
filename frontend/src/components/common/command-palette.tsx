/**
 * `CommandPalette`: press Cmd/Ctrl+K (or use the header button) and type to jump to any page or
 * project. It lists every page of the current project (when you are inside one), the account
 * pages, and all of the user's projects. Mounted once by the app frame. To open it from your own
 * button call `openCommandPalette()`.
 */
"use client"

import { FolderKanban } from "lucide-react"
import { usePathname, useRouter } from "next/navigation"
import { useEffect, useState } from "react"

import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { useProjects } from "@/features/projects/hooks"
import { ACCOUNT_NAV, ALL_PROJECT_PAGES, PROJECTS_NAV, projectHref } from "@/lib/nav"

const OPEN_EVENT = "verano:command-palette"

/** Opens the palette from anywhere (a button, a menu item). */
export function openCommandPalette(): void {
  window.dispatchEvent(new Event(OPEN_EVENT))
}

export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const router = useRouter()
  const pathname = usePathname()
  const projects = useProjects(open)
  const projectId = /^\/projects\/([^/]+)/.exec(pathname)?.[1]

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        setOpen((value) => !value)
      }
    }
    const onOpen = () => setOpen(true)
    window.addEventListener("keydown", onKey)
    window.addEventListener(OPEN_EVENT, onOpen)
    return () => {
      window.removeEventListener("keydown", onKey)
      window.removeEventListener(OPEN_EVENT, onOpen)
    }
  }, [])

  function go(href: string) {
    setOpen(false)
    router.push(href)
  }

  return (
    <CommandDialog
      open={open}
      onOpenChange={setOpen}
      title="Go to"
      description="Search pages and projects, then press Enter."
    >
      <Command>
        <CommandInput placeholder="Go to a page or project…" aria-label="Search pages and projects" />
        <CommandList>
          <CommandEmpty>Nothing matches. Try a page name like “results”.</CommandEmpty>
          {projectId ? (
            <CommandGroup heading="Pages in this project">
              {ALL_PROJECT_PAGES.map((page) => (
                <CommandItem
                  key={page.key}
                  value={`${page.label} ${page.subtitle}`}
                  onSelect={() => go(projectHref(projectId, page))}
                >
                  <page.icon aria-hidden />
                  <span>{page.label}</span>
                  <span className="text-text-muted ml-auto hidden truncate text-xs sm:inline">
                    {page.subtitle}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          ) : null}
          <CommandGroup heading="Account">
            <CommandItem value={`${PROJECTS_NAV.label} all projects`} onSelect={() => go(PROJECTS_NAV.href)}>
              <PROJECTS_NAV.icon aria-hidden />
              <span>{PROJECTS_NAV.label}</span>
            </CommandItem>
            {ACCOUNT_NAV.map((page) => (
              <CommandItem
                key={page.key}
                value={`${page.label} ${page.subtitle}`}
                onSelect={() => go(page.href)}
              >
                <page.icon aria-hidden />
                <span>{page.label}</span>
              </CommandItem>
            ))}
          </CommandGroup>
          {projects.data?.items.length ? (
            <CommandGroup heading="Your projects">
              {projects.data.items.map((project) => (
                <CommandItem
                  key={project.id}
                  value={`project ${project.name}`}
                  onSelect={() => go(`/projects/${project.id}/keys`)}
                >
                  <FolderKanban aria-hidden />
                  <span className="truncate">{project.name}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          ) : null}
        </CommandList>
      </Command>
    </CommandDialog>
  )
}
