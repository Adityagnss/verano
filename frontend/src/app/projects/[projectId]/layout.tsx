/** Frame for one project's steps: stepper, project name and running cost. */
import type { ReactNode } from "react"

import { ProjectShell } from "@/features/projects/components/project-shell"

export default async function ProjectLayout({
  children,
  params,
}: {
  children: ReactNode
  params: Promise<{ projectId: string }>
}) {
  const { projectId } = await params
  return <ProjectShell projectId={projectId}>{children}</ProjectShell>
}
