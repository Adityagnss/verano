/** Step 5: Run. */
import { RunStep } from "@/features/run/components/run-step"

export default async function RunPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params
  return <RunStep projectId={projectId} />
}
