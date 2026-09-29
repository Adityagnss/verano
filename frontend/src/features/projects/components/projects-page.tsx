/** The projects list, with a one-field form to create a project and open its first step. */
"use client"

import { ArrowRight, FolderKanban, Plus } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import type { FormEvent } from "react"

import { EmptyState } from "@/components/common/empty-state"
import { Logo } from "@/components/common/logo"
import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

import { PROJECTS_COPY } from "../copy"
import { useCreateProject, useProjects } from "../hooks"
import { AccountMenu } from "./account-menu"

const FIRST_STEP = "keys"

export function ProjectsPage() {
  const router = useRouter()
  const projects = useProjects()
  const create = useCreateProject()

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const name = String(new FormData(event.currentTarget).get("name")).trim()
    const project = await create.mutateAsync(name)
    router.push(`/projects/${project.id}/${FIRST_STEP}`)
  }

  const items = projects.data?.items ?? []
  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-8 px-4 py-8 sm:px-6 sm:py-10">
      <header className="flex items-center justify-between gap-4">
        <Logo size={32} />
        <AccountMenu />
      </header>
      <section className="from-lagoon-soft to-card ring-lagoon/15 flex flex-col gap-2 rounded-2xl bg-gradient-to-br px-6 py-7 ring-1 sm:px-8">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{PROJECTS_COPY.title}</h1>
        <p className="text-text-secondary max-w-2xl text-[0.95rem]">{PROJECTS_COPY.subtitle}</p>
      </section>
      <ErrorMessage error={projects.error} />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <form
          onSubmit={(event) => void submit(event).catch(() => undefined)}
          className="border-lagoon/40 bg-card flex flex-col justify-between gap-3 rounded-2xl border border-dashed p-5"
        >
          <div className="flex items-center gap-2.5">
            <span className="bg-lagoon-soft text-lagoon-strong flex size-9 items-center justify-center rounded-xl">
              <Plus className="size-5" />
            </span>
            <Label htmlFor="name" className="text-base font-semibold">
              {PROJECTS_COPY.nameLabel}
            </Label>
          </div>
          <Input id="name" name="name" placeholder={PROJECTS_COPY.namePlaceholder} required maxLength={200} />
          <ErrorMessage error={create.error} />
          <Button type="submit" size="lg" disabled={create.isPending}>
            {create.isPending ? PROJECTS_COPY.creating : PROJECTS_COPY.create}
          </Button>
        </form>
        {items.map((project) => (
          <Link
            key={project.id}
            href={`/projects/${project.id}/${FIRST_STEP}`}
            className="bg-card ring-border hover:ring-lagoon/40 group flex flex-col justify-between gap-6 rounded-2xl p-5 ring-1 transition-all hover:-translate-y-0.5 hover:shadow-md"
          >
            <div className="flex items-start justify-between gap-3">
              <span className="from-lagoon to-lagoon-strong flex size-9 items-center justify-center rounded-xl bg-gradient-to-br text-white shadow-sm">
                <FolderKanban className="size-[1.125rem]" />
              </span>
              <ArrowRight className="text-text-muted group-hover:text-lagoon-strong size-4 transition-colors" />
            </div>
            <div className="min-w-0">
              <h2 className="truncate text-base font-semibold">{project.name}</h2>
              <p className="text-text-muted mt-0.5 text-xs">
                {project.description ?? `Created ${new Date(project.created_at).toLocaleDateString()}`}
              </p>
            </div>
          </Link>
        ))}
      </div>
      {projects.isSuccess && items.length === 0 ? (
        <EmptyState title={PROJECTS_COPY.emptyTitle} description={PROJECTS_COPY.emptyDescription} />
      ) : null}
    </main>
  )
}
