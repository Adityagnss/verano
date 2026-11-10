/**
 * Add examples: an optional wizard (choose what you have, upload, match the columns,
 * confirm). Data is optional, so "Skip" goes straight to the test cases.
 */
"use client"

import { useRouter } from "next/navigation"
import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { PageIntro } from "@/components/common/page-intro"
import { StatusBadge } from "@/components/common/status-badge"
import { Wizard } from "@/components/common/wizard"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { ALL_PROJECT_PAGES, projectHref } from "@/lib/nav"

import { DATA_COPY } from "../copy"
import { isBusy, useFiles } from "../hooks"
import { FileList } from "./file-list"
import { UploadCards } from "./upload-cards"

const PAGE = ALL_PROJECT_PAGES.find((p) => p.key === "data")!
const NEXT = ALL_PROJECT_PAGES.find((p) => p.key === "tests")!
type Kind = keyof typeof DATA_COPY.cards
const KINDS: Kind[] = ["inputs", "golden", "documents"]
const DONE = new Set(["imported", "extracted"])

export function DataStep({ projectId }: { projectId: string }) {
  const router = useRouter()
  const files = useFiles(projectId)
  const list = files.data ?? []
  const [kinds, setKinds] = useState<Kind[]>([])
  const [position, setPosition] = useState<number | null>(null)
  const hasData = list.some((f) => DONE.has(f.status))
  const next = () => router.push(projectHref(projectId, NEXT))
  const step = position ?? (list.length > 0 ? 2 : 0)
  const shown = kinds.length ? kinds : KINDS

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <PageIntro
        storageKey="data"
        title={PAGE.label}
        what={DATA_COPY.intro.what}
        whenToUse={DATA_COPY.intro.whenToUse}
        youGet={DATA_COPY.intro.youGet}
        learnMore="data"
        hasContent={list.length > 0}
        primaryAction={
          <Button variant="outline" size="lg" className="min-h-10" onClick={next}>
            {DATA_COPY.skip}
          </Button>
        }
      />
      <ErrorMessage error={files.error} />
      <Wizard
        step={step}
        onStepChange={setPosition}
        finishLabel={DATA_COPY.next}
        onFinish={next}
        steps={[
          {
            id: "choose",
            title: DATA_COPY.wizard.chooseTitle,
            description: DATA_COPY.wizard.chooseDescription,
            content: (
              <ul className="flex flex-col gap-3">
                {KINDS.map((kind) => (
                  <li key={kind} className="bg-card ring-border rounded-lg p-3 ring-1">
                    <label className="flex min-h-10 items-start gap-3">
                      <Checkbox
                        aria-label={DATA_COPY.cards[kind].title}
                        checked={kinds.includes(kind)}
                        onCheckedChange={(checked) =>
                          setKinds(checked ? [...kinds, kind] : kinds.filter((k) => k !== kind))
                        }
                      />
                      <span>
                        <span className="block text-sm font-medium">{DATA_COPY.cards[kind].title}</span>
                        <span className="text-text-muted block text-xs">
                          {DATA_COPY.cards[kind].description}
                        </span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            ),
            validate: () => (kinds.length > 0 || list.length > 0 ? true : DATA_COPY.wizard.chooseNone),
          },
          {
            id: "upload",
            title: DATA_COPY.wizard.uploadTitle,
            description: DATA_COPY.wizard.uploadDescription,
            content: (
              <div className="flex flex-col gap-4">
                <UploadCards projectId={projectId} kinds={shown} />
                <FileList projectId={projectId} files={list} />
              </div>
            ),
            validate: () => (list.length > 0 ? true : DATA_COPY.wizard.uploadNone),
          },
          {
            id: "match",
            title: DATA_COPY.wizard.matchTitle,
            description: DATA_COPY.wizard.matchDescription,
            content: <FileList projectId={projectId} files={list} />,
            validate: () => (list.some(isBusy) ? DATA_COPY.wizard.waiting : true),
          },
          {
            id: "confirm",
            title: DATA_COPY.wizard.confirmTitle,
            description: DATA_COPY.wizard.confirmDescription,
            content: (
              <ul className="flex flex-col gap-2">
                {list.map((file) => (
                  <li key={file.id} className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="min-w-0 truncate font-medium">{file.filename}</span>
                    <StatusBadge tone={DONE.has(file.status) ? "success" : "neutral"}>
                      {DATA_COPY.status[file.status]}
                    </StatusBadge>
                  </li>
                ))}
                {hasData ? null : <li className="text-text-muted text-sm">{DATA_COPY.wizard.confirmNone}</li>}
              </ul>
            ),
          },
        ]}
      />
      {hasData ? null : (
        <Button variant="link" className="min-h-10 self-start px-0" onClick={next}>
          {DATA_COPY.generateForMe}
        </Button>
      )}
    </div>
  )
}
