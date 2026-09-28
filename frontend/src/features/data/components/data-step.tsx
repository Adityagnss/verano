/**
 * Step 3, Your Data: three optional upload cards, then each file's column mapping and
 * validation report. Data is optional, so "generate it for me" skips straight to test cases.
 */
"use client"

import { useRouter } from "next/navigation"

import { ErrorMessage } from "@/components/common/error-message"
import { PageActions } from "@/components/common/page-actions"
import { Button } from "@/components/ui/button"
import { useCurrentPrompt } from "@/features/prompt/hooks"

import { DATA_COPY } from "../copy"
import { useFiles } from "../hooks"
import { FileList } from "./file-list"
import { UploadCards } from "./upload-cards"

export function DataStep({ projectId }: { projectId: string }) {
  const router = useRouter()
  const files = useFiles(projectId)
  const prompt = useCurrentPrompt(projectId)
  const promptVersionId = prompt.data?.latest_version.id ?? null
  const hasData = (files.data ?? []).some((f) => f.status === "imported" || f.status === "extracted")
  const next = () => router.push(`/projects/${projectId}/tests`)
  return (
    <div className="flex max-w-5xl flex-col gap-8">
      <div>
        <h2 className="text-xl font-semibold">{DATA_COPY.title}</h2>
        <p className="text-muted-foreground mt-1 max-w-3xl text-sm">{DATA_COPY.subtitle}</p>
      </div>
      <ErrorMessage error={files.error ?? prompt.error} />
      <UploadCards projectId={projectId} />
      <section className="flex flex-col gap-3">
        <h3 className="text-sm font-medium">{DATA_COPY.filesHeading}</h3>
        <FileList projectId={projectId} files={files.data ?? []} promptVersionId={promptVersionId} />
      </section>
      <PageActions
        summary={
          hasData ? null : (
            <Button variant="link" className="px-0" onClick={next}>
              {DATA_COPY.generateForMe}
            </Button>
          )
        }
      >
        <Button size="lg" onClick={next}>
          {DATA_COPY.next}
        </Button>
      </PageActions>
    </div>
  )
}
