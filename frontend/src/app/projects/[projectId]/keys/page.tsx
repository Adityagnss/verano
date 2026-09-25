/** Step 1: Keys. */
import { KeysStep } from "@/features/keys/components/keys-step"

export default async function KeysPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params
  return <KeysStep projectId={projectId} />
}
