/** Logbook: every answer, model call and score, filterable, with analysis. */
import { LogbookPage } from "@/features/logbook/components/logbook-page"

export default async function Page({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params
  return <LogbookPage projectId={projectId} />
}
