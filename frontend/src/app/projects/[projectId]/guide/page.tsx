/** Prompt guide: which prompt techniques help, with evidence. */
import { GuidePage } from "@/features/guide/components/guide-page"

export default async function Page({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params
  return <GuidePage projectId={projectId} />
}
