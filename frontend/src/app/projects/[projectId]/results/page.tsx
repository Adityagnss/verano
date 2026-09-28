/** Step 6: Results. `?experiment=<id>` opens one experiment; otherwise the latest finished one. */
import { ResultsStep } from "@/features/results/components/results-step"

export default async function ResultsPage({
  params,
  searchParams,
}: {
  params: Promise<{ projectId: string }>
  searchParams: Promise<{ experiment?: string }>
}) {
  const { projectId } = await params
  const { experiment } = await searchParams
  return <ResultsStep projectId={projectId} experimentId={experiment ?? null} />
}
