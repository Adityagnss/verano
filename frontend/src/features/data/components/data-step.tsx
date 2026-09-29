/**
 * Step 3, Your Data: three optional upload cards, then the golden set's column mapping and
 * report. Data is optional, so "generate it for me" skips straight to test cases.
 */
"use client"

import { useRouter } from "next/navigation"

import { ErrorMessage } from "@/components/common/error-message"
import { PageActions } from "@/components/common/page-actions"
import { Section } from "@/components/common/section"
import { StepHeader } from "@/components/common/step-header"
import { Button } from "@/components/ui/button"

import { DATA_COPY } from "../copy"
import { useFiles } from "../hooks"
import { FileList } from "./file-list"
import { UploadCards } from "./upload-cards"

export function DataStep({ projectId }: { projectId: string }) {
  const router = useRouter()
  const files = useFiles(projectId)
  const hasData = (files.data ?? []).some((f) => f.status === "imported" || f.status === "extracted")
  const next = () => router.push(`/projects/${projectId}/tests`)
  return (
    <div className="mx-auto flex w-full max-w-[96rem] flex-col gap-6">
      <StepHeader
        step="data"
        title={DATA_COPY.title}
        description={DATA_COPY.subtitle}
        howItWorks={DATA_COPY.howItWorks}
      />
      <ErrorMessage error={files.error} />
      <Section number={1} title={DATA_COPY.uploadHeading} description={DATA_COPY.uploadHint}>
        <UploadCards projectId={projectId} />
      </Section>
      <Section number={2} title={DATA_COPY.filesHeading} description={DATA_COPY.filesHint}>
        <FileList projectId={projectId} files={files.data ?? []} />
      </Section>
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
