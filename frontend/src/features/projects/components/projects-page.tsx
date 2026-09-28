/** The projects list, with a one-field form to create a project and open its first step. */
"use client"

import { ArrowRight } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import type { FormEvent } from "react"

import { EmptyState } from "@/components/common/empty-state"
import { Logo } from "@/components/common/logo"
import { ErrorMessage } from "@/components/common/error-message"
import { PageActions } from "@/components/common/page-actions"
import { Button } from "@/components/ui/button"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
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
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col gap-6 px-6 py-10">
      <header className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <Logo size={32} className="[&>span]:hidden" />
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{PROJECTS_COPY.title}</h1>
            <p className="text-text-secondary mt-1 text-sm">{PROJECTS_COPY.subtitle}</p>
          </div>
        </div>
        <AccountMenu />
      </header>
      <ErrorMessage error={projects.error} />
      {projects.isSuccess && items.length === 0 ? (
        <EmptyState title={PROJECTS_COPY.emptyTitle} description={PROJECTS_COPY.emptyDescription} />
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        {items.map((project) => (
          <Link key={project.id} href={`/projects/${project.id}/${FIRST_STEP}`}>
            <Card className="hover:ring-primary/40 transition-shadow hover:shadow-md">
              <CardHeader>
                <CardTitle className="flex items-center justify-between gap-2">
                  {project.name}
                  <ArrowRight className="text-text-muted size-4" />
                </CardTitle>
                {project.description ? <CardDescription>{project.description}</CardDescription> : null}
              </CardHeader>
            </Card>
          </Link>
        ))}
      </div>
      <form onSubmit={(event) => void submit(event).catch(() => undefined)}>
        <PageActions
          summary={
            <div className="flex w-full max-w-lg flex-col gap-1.5">
              <Label htmlFor="name">{PROJECTS_COPY.nameLabel}</Label>
              <Input
                id="name"
                name="name"
                placeholder={PROJECTS_COPY.namePlaceholder}
                required
                maxLength={200}
              />
              <ErrorMessage error={create.error} />
            </div>
          }
        >
          <Button type="submit" size="lg" disabled={create.isPending}>
            {create.isPending ? PROJECTS_COPY.creating : PROJECTS_COPY.create}
          </Button>
        </PageActions>
      </form>
    </main>
  )
}
