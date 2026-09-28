/** Step 7: Improve. `?experiment=<id>` improves from that experiment; otherwise the latest finished one. */
import { ImproveStep } from "@/features/improve/components/improve-step"

export default async function ImprovePage({
  params,
  searchParams,
}: {
  params: Promise<{ projectId: string }>
  searchParams: Promise<{ experiment?: string }>
}) {
  const { projectId } = await params
  const { experiment } = await searchParams
  return <ImproveStep projectId={projectId} experimentId={experiment ?? null} />
}
