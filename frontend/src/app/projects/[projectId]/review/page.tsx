/** Review queue: answers to label, progress and disagreements. */
import { ReviewStep } from "@/features/review/components/review-step"

export default async function Page({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params
  return <ReviewStep projectId={projectId} />
}
