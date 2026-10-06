/**
 * Prompt versions on the dashboard: every version at a glance (each model's quality and pass rate in the
 * latest finished run of that version), and any two runs compared per model with the same "clear
 * difference" rule as everywhere else, plus how many test cases got fixed or broken.
 */
"use client"

import { useQuery } from "@tanstack/react-query"
import { ArrowRight } from "lucide-react"
import { useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { StatusBadge } from "@/components/common/status-badge"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/select"
import { ComparisonDetail } from "@/features/results/components/comparison-detail"
import { api, call } from "@/lib/api/client"
import type { ComparisonOut } from "@/lib/api/types"
import { cn } from "@/lib/utils"

import type { Finished } from "../domain"
import { pct } from "../domain"

function versionNumber(label: string): number {
  return Number(label.replace(/^v/, "")) || 0
}

/** The newest finished run of each prompt version, oldest version first. */
export function latestPerVersion(finished: Finished[]): Finished[] {
  const by = new Map<string, Finished>()
  for (const f of finished) by.set(f.label, f) // `finished` is oldest first, so the last one wins
  return [...by.values()].sort((a, b) => versionNumber(a.label) - versionNumber(b.label))
}

function useComparison(projectId: string, newer: string | null, older: string | null) {
  return useQuery({
    queryKey: ["projects", projectId, "compare", newer, older],
    enabled: Boolean(newer && older && newer !== older),
    queryFn: () =>
      call(() =>
        api.GET("/api/v1/projects/{project_id}/experiments/{experiment_id}/compare", {
          params: {
            path: { project_id: projectId, experiment_id: newer ?? "" },
            query: { against: older ?? "" },
          },
        }),
      ),
  })
}

function verdict(c: ComparisonOut): { text: string; tone: "success" | "danger" | "neutral" } {
  if (c.label === "clear difference") {
    return c.first_better
      ? { text: "Clearly better", tone: "success" }
      : { text: "Clearly worse", tone: "danger" }
  }
  if (c.label === "too few cases") return { text: "Too few cases to tell", tone: "neutral" }
  return { text: "No clear difference", tone: "neutral" }
}

function runLabel(f: Finished): string {
  return `${f.label.toUpperCase()}, ${f.experiment.name}, ${new Date(f.experiment.created_at).toLocaleDateString()}`
}

export function VersionsPanel({ projectId, finished }: { projectId: string; finished: Finished[] }) {
  const versions = latestPerVersion(finished)
  const models = [...new Set(versions.flatMap((v) => v.results.models.map((m) => m.model)))].sort()
  const newest = [...finished].reverse()
  const [newer, setNewer] = useState<string>("")
  const [older, setOlder] = useState<string>("")
  const defaultNewer = versions.at(-1)?.experiment.id ?? ""
  const defaultOlder = versions.at(-2)?.experiment.id ?? ""
  const pickedNewer = newer || defaultNewer
  const pickedOlder = older || defaultOlder
  const compared = useComparison(projectId, pickedNewer || null, pickedOlder || null)
  const label = (id: string) => finished.find((f) => f.experiment.id === id)?.label.toUpperCase() ?? ""

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h4 className="text-sm font-semibold">All versions at a glance</h4>
        <p className="text-text-muted text-xs">
          Each model in the latest finished run of each version: quality, and pass rate below it. The best
          version for each model is marked.
        </p>
        <div className="border-border overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-border text-text-secondary border-b text-left">
                <th scope="col" className="px-3 py-2 font-medium">
                  Model
                </th>
                {versions.map((v) => (
                  <th key={v.experiment.id} scope="col" className="px-3 py-2 text-right font-medium">
                    {v.label.toUpperCase()}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {models.map((model) => {
                const cells = versions.map((v) => v.results.models.find((m) => m.model === model) ?? null)
                const best = Math.max(...cells.map((c) => c?.quality ?? -1))
                return (
                  <tr key={model} className="border-border border-b last:border-b-0">
                    <th scope="row" className="px-3 py-2 text-left font-medium">
                      {model}
                    </th>
                    {cells.map((cell, i) => (
                      <td
                        key={versions[i].experiment.id}
                        className={cn(
                          "px-3 py-2 text-right tabular-nums",
                          cell && cell.quality !== null && cell.quality === best && versions.length > 1
                            ? "bg-marigold-soft/60"
                            : "",
                        )}
                      >
                        {cell ? (
                          <span className="flex flex-col items-end">
                            <span className="font-semibold">{pct(cell.quality)}</span>
                            <span className="text-text-muted text-xs">{pct(cell.pass_rate)} passed</span>
                          </span>
                        ) : (
                          <span className="text-text-muted">not run</span>
                        )}
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <h4 className="text-sm font-semibold">Compare two runs</h4>
        <p className="text-text-muted text-xs">
          Usually two prompt versions on the same test cases. Only cases judged in both runs count, and they
          must have been scored with the same checks and judge.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="older">Before</Label>
            <NativeSelect
              id="older"
              value={pickedOlder}
              onChange={(e) => setOlder(e.target.value)}
              className="h-9 w-72"
            >
              {newest.map((f) => (
                <option key={f.experiment.id} value={f.experiment.id}>
                  {runLabel(f)}
                </option>
              ))}
            </NativeSelect>
          </div>
          <ArrowRight className="text-text-muted mb-2.5 size-4" aria-hidden />
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="newer">After</Label>
            <NativeSelect
              id="newer"
              value={pickedNewer}
              onChange={(e) => setNewer(e.target.value)}
              className="h-9 w-72"
            >
              {newest.map((f) => (
                <option key={f.experiment.id} value={f.experiment.id}>
                  {runLabel(f)}
                </option>
              ))}
            </NativeSelect>
          </div>
        </div>
        {pickedNewer && pickedNewer === pickedOlder ? (
          <p className="text-text-muted text-sm">Pick two different runs.</p>
        ) : null}
        <ErrorMessage error={compared.error} />
        {compared.data ? (
          <div className="flex flex-col gap-3">
            {!compared.data.same_test_cases ? (
              <p className="text-warning-strong text-sm">
                These runs used different test cases, so only the cases they share are compared.
              </p>
            ) : null}
            {compared.data.models.length === 0 ? (
              <p className="text-text-muted text-sm">These two runs have no model in common.</p>
            ) : null}
            <ul className="flex flex-col gap-3">
              {compared.data.models.map((m) => {
                const c = m.comparison
                const v = verdict(c)
                const before = c.difference === null ? null : (c.pass_rate_difference ?? null)
                return (
                  <li
                    key={m.model_profile_id}
                    className="border-border flex flex-col gap-2 rounded-lg border p-4"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <span className="font-medium">{m.model}</span>
                      <StatusBadge tone={v.tone}>{v.text}</StatusBadge>
                    </div>
                    <p className="text-sm">
                      {label(pickedOlder)} to {label(pickedNewer)}: quality{" "}
                      <span className="font-semibold tabular-nums">
                        {c.difference === null
                          ? "—"
                          : `${c.difference >= 0 ? "+" : ""}${Math.round(c.difference * 100)} points`}
                      </span>
                      {before !== null ? (
                        <span className="text-text-secondary">
                          , pass rate {before >= 0 ? "+" : ""}
                          {Math.round(before * 100)} points
                        </span>
                      ) : null}
                      . {m.fixed.length} {m.fixed.length === 1 ? "case" : "cases"} fixed, {m.broken.length}{" "}
                      {m.broken.length === 1 ? "case" : "cases"} broken.
                    </p>
                    <ComparisonDetail comparison={c} />
                  </li>
                )
              })}
            </ul>
          </div>
        ) : null}
      </div>
    </div>
  )
}
