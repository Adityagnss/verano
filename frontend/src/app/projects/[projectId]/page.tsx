/** Project Home: the pipeline, the next step and the latest runs. */
import { ProjectHome } from "@/features/home/project-home"

export default async function ProjectPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params
  return <ProjectHome projectId={projectId} />
}
