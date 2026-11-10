/** Import a file of traffic: pick the format (or let Verano work it out), see what was imported and every problem. */
"use client"

import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

import { TRAFFIC_COPY as C } from "../copy"
import { useFormats, useImport } from "../hooks"

export function ImportDialog({ projectId }: { projectId: string }) {
  const formats = useFormats(projectId)
  const run = useImport(projectId)
  const [file, setFile] = useState<File | null>(null)
  const [format, setFormat] = useState("auto")
  const [version, setVersion] = useState("")
  const report = run.data
  return (
    <Dialog>
      <DialogTrigger render={<Button size="lg">{C.import}</Button>} />
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{C.importTitle}</DialogTitle>
          <DialogDescription>{C.importDescription}</DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (file) run.mutate({ file, format, promptVersion: version.trim() })
          }}
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="traffic-format">{C.formatLabel}</Label>
            <select
              id="traffic-format"
              className="border-input bg-background h-9 rounded-lg border px-3 text-sm"
              value={format}
              onChange={(e) => setFormat(e.target.value)}
            >
              <option value="auto">{C.auto}</option>
              {(formats.data ?? []).map((f) => (
                <option key={f.name} value={f.name}>
                  {f.label}
                </option>
              ))}
            </select>
            <p className="text-text-muted text-xs">
              {(formats.data ?? []).find((f) => f.name === format)?.hint ??
                (format === "auto" ? "Verano looks at the file and picks the format for you." : "")}
            </p>
            {(formats.data ?? []).length ? (
              <ul className="flex flex-col gap-1 text-xs" aria-label="Supported formats">
                {(formats.data ?? []).map((f) => (
                  <li key={f.name} className="flex flex-wrap items-baseline gap-2">
                    <StatusBadge>{f.label}</StatusBadge>
                    <span className="text-text-secondary min-w-0">{f.hint}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="traffic-file">{C.fileLabel}</Label>
            <Input
              id="traffic-file"
              type="file"
              accept=".json,.jsonl,.har"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="traffic-version">{C.versionLabel}</Label>
            <Input id="traffic-version" value={version} onChange={(e) => setVersion(e.target.value)} />
            <p className="text-text-muted text-xs">{C.versionHint}</p>
          </div>
          <Button type="submit" size="lg" disabled={!file || run.isPending}>
            {run.isPending ? C.importing : C.import}
          </Button>
        </form>
        <ErrorMessage error={run.error} />
        {report ? (
          <div className="flex flex-col gap-3 text-sm" role="status">
            <p className="font-medium">
              {C.importDone(report.imported)} Read as {report.format_label}.
            </p>
            <ul className="text-text-secondary list-disc pl-5">
              <li>{report.found} records found</li>
              {report.duplicates ? <li>{report.duplicates} already imported earlier, skipped</li> : null}
              {report.ignored ? <li>{report.ignored} spans were not model calls, ignored</li> : null}
              {report.scrubbed ? <li>{report.scrubbed} pieces of personal data removed</li> : null}
              {report.truncated ? <li>{report.truncated} long texts were cut to the size limit</li> : null}
            </ul>
            {report.problems.length ? (
              <div>
                <p className="font-medium">{C.problemsTitle}</p>
                <ul className="text-text-secondary list-disc pl-5">
                  {report.problems.map((p) => (
                    <li key={`${p.record}-${p.message}`}>
                      Record {p.record}: {p.message}
                    </li>
                  ))}
                  {report.more_problems ? <li>…and {report.more_problems} more</li> : null}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
