/** Step 2: Prompt, with the labels that decide which version an app receives. */
import { LabelsPanel } from "@/features/labels/components/labels-panel"
import { PromptStep } from "@/features/prompt/components/prompt-step"

export default async function PromptPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params
  return (
    <div className="flex flex-col gap-6">
      <PromptStep projectId={projectId} />
      <div className="mx-auto w-full max-w-[96rem]">
        <LabelsPanel projectId={projectId} />
      </div>
    </div>
  )
}
