/** Opening a project starts at its first step. */
import { redirect } from "next/navigation"

export default async function ProjectPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params
  redirect(`/projects/${projectId}/keys`)
}
