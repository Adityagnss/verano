/** Your apps: connect an app that Verano tests over HTTP. */
import { AppsStep } from "@/features/apps/components/apps-step"

export default async function Page({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params
  return <AppsStep projectId={projectId} />
}
