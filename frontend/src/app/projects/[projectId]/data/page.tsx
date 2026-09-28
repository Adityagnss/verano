/** Step 3: Your Data. */
import { DataStep } from "@/features/data/components/data-step"

export default async function DataPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params
  return <DataStep projectId={projectId} />
}
