/** Step 4: Test Cases. */
import { TestsStep } from "@/features/tests/components/tests-step"

export default async function TestsPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params
  return <TestsStep projectId={projectId} />
}
