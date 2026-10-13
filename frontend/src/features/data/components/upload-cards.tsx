/**
 * The three optional upload cards (DEVELOPMENT.md 2.2): input files (each sent to the models
 * as one attachment), the golden set (correct answers, one per input file) and reference
 * documents.
 */
"use client"

import { Upload } from "lucide-react"
import { useRef, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { UploadPurpose } from "@/lib/api/types"

import { DATA_COPY } from "../copy"
import { inputPurpose } from "../domain"
import { useUpload } from "../hooks"

const GOLDEN_ACCEPT = ".csv,.tsv,.xlsx,.json,.jsonl,.ndjson"
const INPUT_ACCEPT = `${GOLDEN_ACCEPT},.txt,.md,.markdown`
const DOCUMENT_ACCEPT = ".pdf,.docx,.txt,.md,.markdown"
const CARDS: {
  key: keyof typeof DATA_COPY.cards
  purpose: UploadPurpose
  accept: string
  formats: string
}[] = [
  { key: "inputs", purpose: "input", accept: INPUT_ACCEPT, formats: DATA_COPY.inputFormats },
  { key: "golden", purpose: "golden", accept: GOLDEN_ACCEPT, formats: DATA_COPY.goldenFormats },
  { key: "documents", purpose: "document", accept: DOCUMENT_ACCEPT, formats: DATA_COPY.documentFormats },
]

function UploadCard({ projectId, card }: { projectId: string; card: (typeof CARDS)[number] }) {
  const input = useRef<HTMLInputElement>(null)
  const upload = useUpload(projectId)
  const [wholeFile, setWholeFile] = useState(false)
  async function send(files: FileList | null) {
    for (const file of Array.from(files ?? [])) {
      const purpose = card.purpose === "input" ? inputPurpose(file.name, wholeFile) : card.purpose
      await upload.mutateAsync({ file, purpose })
      toast.success(DATA_COPY.uploaded(file.name))
    }
    if (input.current) input.current.value = ""
  }
  const copy = DATA_COPY.cards[card.key]
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>{copy.title}</CardTitle>
        <CardDescription>{copy.description}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <span className="text-muted-foreground text-xs">{card.formats}</span>
        <input
          ref={input}
          type="file"
          accept={card.accept}
          multiple
          hidden
          data-testid={`upload-${card.key}`}
          onChange={(event) =>
            void send(event.target.files).catch((error: Error) => toast.error(error.message))
          }
        />
        {card.purpose === "input" ? (
          <fieldset className="flex flex-col gap-1.5">
            <legend className="mb-1 text-xs font-medium">{DATA_COPY.tableChoice.legend}</legend>
            {([false, true] as const).map((whole) => {
              const choice = whole ? DATA_COPY.tableChoice.whole : DATA_COPY.tableChoice.rows
              return (
                <label key={String(whole)} className="flex items-start gap-2 text-xs">
                  <input
                    type="radio"
                    name="table-choice"
                    className="accent-lagoon mt-0.5"
                    checked={wholeFile === whole}
                    onChange={() => setWholeFile(whole)}
                  />
                  <span>
                    <span className="font-medium">{choice.label}</span>
                    <span className="text-text-muted block">{choice.hint}</span>
                  </span>
                </label>
              )
            })}
          </fieldset>
        ) : null}
        <Button variant="outline" onClick={() => input.current?.click()} disabled={upload.isPending}>
          <Upload />
          {upload.isPending ? DATA_COPY.uploading : DATA_COPY.choose}
        </Button>
      </CardContent>
    </Card>
  )
}

export function UploadCards({ projectId }: { projectId: string }) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {CARDS.map((card) => (
        <UploadCard key={card.key} projectId={projectId} card={card} />
      ))}
    </div>
  )
}
