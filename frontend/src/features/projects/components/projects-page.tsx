/** The projects list, with a one-field form to create a project and open its first step. */
"use client"

import { ArrowRight, FolderKanban, Plus } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import type { FormEvent } from "react"

import { EmptyState } from "@/components/common/empty-state"
import { PageIntro } from "@/components/common/page-intro"
import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

import { PROJECTS_COPY } from "../copy"
import { useCreateProject, useProjects } from "../hooks"
import { AccountFrame } from "./account-frame"

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
    <AccountFrame>
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8">
        <PageIntro
          storageKey="projects"
          title={PROJECTS_COPY.title}
          what={PROJECTS_COPY.subtitle}
          whenToUse="you start testing a new prompt, chatbot or model choice"
          youGet="one place for the keys, prompt, test cases and results of that use case"
          learnMore="projects"
          hasContent={items.length > 0}
        />
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
            <Input
              id="name"
              name="name"
              placeholder={PROJECTS_COPY.namePlaceholder}
              required
              maxLength={200}
            />
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
          <EmptyState
            icon={FolderKanban}
            title={PROJECTS_COPY.emptyTitle}
            description={PROJECTS_COPY.emptyDescription}
          />
        ) : null}
      </div>
    </AccountFrame>
  )
}
