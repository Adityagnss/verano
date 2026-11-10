/**
 * The projects list. First visit: a welcome with three ways to start. Later: a grid of project cards with
 * progress, last run and spend. A project always starts from one name field.
 */
"use client"

import { FolderKanban, GitCompareArrows, MessageSquareText, Terminal } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState, type FormEvent } from "react"

import { CopyButton } from "@/components/common/copy-button"
import { ErrorMessage } from "@/components/common/error-message"
import { PageIntro } from "@/components/common/page-intro"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useExperiments } from "@/features/run/hooks"
import { formatCost } from "@/lib/format"

import { PROJECTS_COPY } from "../copy"
import { ProjectActions } from "./project-actions"
import { useCostSummary, useCreateProject, useProjects, useStepCompletion } from "../hooks"
import { AccountFrame } from "./account-frame"

export const CLI_COMMANDS = ["verano login", "verano init", "verano push"]
const DEFAULT_NAME = "My first project"

/** The name to use when the field is left empty: never one the account already has. */
export function freeDefaultName(taken: string[]): string {
  const used = new Set(taken.map((n) => n.trim().toLowerCase()))
  if (!used.has(DEFAULT_NAME.toLowerCase())) return DEFAULT_NAME
  for (let n = 2; ; n++) if (!used.has(`my project ${n}`)) return `My project ${n}`
}

function ProgressRing({ done, total }: { done: number; total: number }) {
  const radius = 14
  const length = 2 * Math.PI * radius
  return (
    <span className="relative inline-flex size-10 shrink-0 items-center justify-center">
      <svg viewBox="0 0 36 36" className="size-10 -rotate-90" aria-hidden>
        <circle cx="18" cy="18" r={radius} fill="none" strokeWidth="3" className="stroke-border" />
        <circle
          cx="18"
          cy="18"
          r={radius}
          fill="none"
          strokeWidth="3"
          strokeLinecap="round"
          className="stroke-lagoon"
          strokeDasharray={length}
          strokeDashoffset={length * (1 - done / total)}
        />
      </svg>
      <span className="absolute text-[0.65rem] font-semibold">
        {done}/{total}
      </span>
    </span>
  )
}

function ProjectCard({ id, name }: { id: string; name: string }) {
  const steps = useStepCompletion(id)
  const runs = useExperiments(id)
  const cost = useCostSummary(id)
  const done = steps.data ? Object.values(steps.data).filter(Boolean).length : 0
  const last = runs.data?.[0]
  return (
    <div className="bg-card ring-border hover:ring-lagoon/40 relative flex min-h-32 rounded-2xl ring-1">
      <Link href={`/projects/${id}`} className="flex w-full flex-col justify-between gap-4 rounded-2xl p-5">
        <div className="flex items-start justify-between gap-3">
          <h2 className="min-w-0 truncate text-base font-semibold">{name}</h2>
          <span role="img" aria-label={`${done} of 7 steps done`}>
            <ProgressRing done={done} total={7} />
          </span>
        </div>
        <dl className="text-text-secondary grid grid-cols-2 gap-2 text-xs">
          <div>
            <dt className="text-text-muted">Last run</dt>
            <dd>{last ? new Date(last.created_at).toLocaleDateString() : "None yet"}</dd>
          </div>
          <div>
            <dt className="text-text-muted">Spent</dt>
            <dd>{cost.data ? formatCost(cost.data.cost) : "-"}</dd>
          </div>
        </dl>
      </Link>
      <div className="absolute right-2 bottom-2">
        <ProjectActions id={id} name={name} />
      </div>
    </div>
  )
}

function PathCard({
  icon: Icon,
  title,
  text,
  onClick,
  disabled,
}: {
  icon: typeof FolderKanban
  title: string
  text: string
  onClick: () => void
  disabled: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="bg-card ring-border hover:ring-lagoon/40 focus-visible:ring-ring flex min-h-32 flex-col items-start gap-2 rounded-2xl p-5 text-left ring-1 disabled:opacity-60"
    >
      <span className="bg-lagoon-soft text-lagoon-strong flex size-9 items-center justify-center rounded-xl">
        <Icon className="size-5" aria-hidden />
      </span>
      <span className="font-semibold">{title}</span>
      <span className="text-text-secondary text-sm">{text}</span>
    </button>
  )
}

export function ProjectsPage() {
  const router = useRouter()
  const projects = useProjects()
  const create = useCreateProject()
  const [name, setName] = useState("")
  const [cliProject, setCliProject] = useState<string | null>(null)

  async function start(destination: string | null) {
    const project = await create.mutateAsync(
      name.trim() || freeDefaultName((projects.data?.items ?? []).map((p) => p.name)),
    )
    if (destination === null) setCliProject(project.id)
    else router.push(`/projects/${project.id}/${destination}`)
  }
  const go = (destination: string | null) => void start(destination).catch(() => undefined)

  function submit(event: FormEvent) {
    event.preventDefault()
    go("keys")
  }

  const items = projects.data?.items ?? []
  const first = projects.isSuccess && items.length === 0
  return (
    <AccountFrame>
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8">
        <PageIntro
          storageKey="projects"
          title={first ? "Welcome to Verano" : PROJECTS_COPY.title}
          what="Verano tests your prompt on the models you choose, using your own test cases, and proves an improvement before you ship it."
          whenToUse="you start testing a new prompt, chatbot or model choice"
          youGet="one place for the keys, prompt, test cases and results of that use case"
          learnMore="projects"
          hasContent={items.length > 0}
        />
        <ErrorMessage error={projects.error} />
        <form onSubmit={submit} className="flex flex-col gap-2 sm:max-w-xl">
          <Label htmlFor="name" className="text-base font-semibold">
            {PROJECTS_COPY.nameLabel}
          </Label>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              id="name"
              name="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={PROJECTS_COPY.namePlaceholder}
              maxLength={200}
              className="h-10"
            />
            <Button type="submit" size="lg" className="min-h-10" disabled={create.isPending}>
              {create.isPending ? PROJECTS_COPY.creating : PROJECTS_COPY.create}
            </Button>
          </div>
          <ErrorMessage error={create.error} />
        </form>

        {first ? (
          <section aria-labelledby="paths" className="flex flex-col gap-3">
            <h2 id="paths" className="text-lg font-semibold">
              Or pick what you want to do first
            </h2>
            <div className="grid gap-4 md:grid-cols-3">
              <PathCard
                icon={GitCompareArrows}
                title="Compare models on a prompt"
                text="Connect providers, write a prompt and see which model does best."
                onClick={() => go("keys")}
                disabled={create.isPending}
              />
              <PathCard
                icon={MessageSquareText}
                title="Test an app I already run"
                text="Point Verano at a chatbot, API or RAG app and test it."
                onClick={() => go("apps")}
                disabled={create.isPending}
              />
              <PathCard
                icon={Terminal}
                title="Bring prompts from my code"
                text="Use the command line to push the prompts in your repository."
                onClick={() => go(null)}
                disabled={create.isPending}
              />
            </div>
          </section>
        ) : null}

        {items.length > 0 ? (
          <section aria-labelledby="yours" className="flex flex-col gap-3">
            <h2 id="yours" className="text-lg font-semibold">
              Your projects
            </h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {items.map((project) => (
                <ProjectCard key={project.id} id={project.id} name={project.name} />
              ))}
            </div>
          </section>
        ) : null}
      </div>

      <Dialog open={cliProject !== null} onOpenChange={(open) => !open && setCliProject(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Bring prompts from your code</DialogTitle>
            <DialogDescription>
              Your project is ready. Run these three commands in your repository.
            </DialogDescription>
          </DialogHeader>
          <ol className="flex flex-col gap-2">
            {CLI_COMMANDS.map((command) => (
              <li
                key={command}
                className="bg-subtle flex items-center justify-between gap-2 rounded-lg px-3 py-2"
              >
                <code className="min-w-0 font-mono text-sm break-all">{command}</code>
                <CopyButton text={command} label="Copy" size="sm" />
              </li>
            ))}
          </ol>
          <Button size="lg" className="min-h-10" onClick={() => router.push(`/projects/${cliProject}`)}>
            Open the project
          </Button>
        </DialogContent>
      </Dialog>
    </AccountFrame>
  )
}
