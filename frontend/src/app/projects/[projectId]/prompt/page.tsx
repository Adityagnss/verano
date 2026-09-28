/** Step 2: Prompt. */
import { PromptStep } from "@/features/prompt/components/prompt-step"

export default async function PromptPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params
  return <PromptStep projectId={projectId} />
}
