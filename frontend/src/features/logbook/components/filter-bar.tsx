/**
 * The filters for Answers and Analysis: a search box, quick result chips, dropdowns for the
 * things you slice by (prompt version, experiment, model, provider, source, category, failed
 * check, call status), a date range, and a chip for every active filter that removes it.
 */
"use client"

import { ChevronDown, Search, X } from "lucide-react"
import { useState } from "react"

import { type Choice, MultiSelect } from "@/components/common/multi-select"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { LogOptions } from "@/lib/api/types"
import { sameConfiguration, shortHash } from "@/lib/config"
import { useBreakpoint } from "@/components/common/use-breakpoint"
import { cn } from "@/lib/utils"

import { LOGBOOK_COPY } from "../copy"
import { type AnswerFilters, EMPTY_FILTERS, activeCount } from "../domain"
import { versionName } from "@/lib/format"

const SOURCES: Choice[] = [
  { value: "golden", label: "Golden", hint: "has your correct answer" },
  { value: "input_file", label: "Your file", hint: "no golden answer" },
  { value: "generated", label: "Generated", hint: "written by Verano" },
  { value: "traffic", label: "From traffic", hint: "a real user question" },
]
const STATUSES: Choice[] = [
  { value: "succeeded", label: "Call worked" },
  { value: "failed", label: "Call failed" },
]

export function FilterBar({
  options,
  filters,
  onChange,
  total,
}: {
  options: LogOptions | undefined
  filters: AnswerFilters
  onChange: (filters: AnswerFilters) => void
  total: number | undefined
}) {
  const set = <K extends keyof AnswerFilters>(key: K, value: AnswerFilters[K]) =>
    onChange({ ...filters, [key]: value })
  const versions = new Map((options?.prompt_versions ?? []).map((v) => [v.id, versionName(v.version)]))
  const chips: { key: string; label: string; remove: () => void }[] = []
  const many = (key: keyof AnswerFilters, name: (v: string) => string) => {
    for (const v of filters[key] as string[])
      chips.push({
        key: `${key}-${v}`,
        label: name(v),
        remove: () => set(key, (filters[key] as string[]).filter((x) => x !== v) as never),
      })
  }
  many("prompt_version_ids", (v) => `Prompt ${versions.get(v) ?? "?"}`)
  many("experiment_ids", (v) => options?.experiments.find((e) => e.id === v)?.name ?? "Experiment")
  many("models", (v) => v)
  many("providers", (v) => v)
  many("sources", (v) => SOURCES.find((s) => s.value === v)?.label ?? v)
  many("categories", (v) => v)
  many("failed_checks", (v) => `Failed: ${v}`)
  many("statuses", (v) => STATUSES.find((s) => s.value === v)?.label ?? v)
  if (filters.passed)
    chips.push({ key: "passed", label: LOGBOOK_COPY.result[filters.passed], remove: () => set("passed", "") })
  if (filters.run_number)
    chips.push({ key: "run", label: `Run ${filters.run_number}`, remove: () => set("run_number", "") })
  if (filters.q) chips.push({ key: "q", label: `“${filters.q}”`, remove: () => set("q", "") })
  if (filters.date_from)
    chips.push({ key: "from", label: `From ${filters.date_from}`, remove: () => set("date_from", "") })
  if (filters.date_to)
    chips.push({ key: "to", label: `To ${filters.date_to}`, remove: () => set("date_to", "") })
  const active = activeCount(filters, EMPTY_FILTERS)
  const { atLeast } = useBreakpoint()
  const [more, setMore] = useState(false)
  const showMore = atLeast("md") || more

  return (
    <div className="bg-card ring-border flex flex-col gap-3 rounded-xl p-3 ring-1">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-0 flex-1 basis-56">
          <Search className="text-text-muted absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <Input
            value={filters.q}
            onChange={(event) => set("q", event.target.value)}
            placeholder={LOGBOOK_COPY.search}
            aria-label={LOGBOOK_COPY.search}
            className="pl-9"
          />
        </div>
        <div className="bg-subtle ring-border flex rounded-lg p-0.5 ring-1" role="group" aria-label="Result">
          {(["", "true", "false"] as const).map((value) => (
            <button
              key={value || "all"}
              type="button"
              aria-pressed={filters.passed === value}
              onClick={() => set("passed", value)}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                filters.passed === value ? "bg-card shadow-sm" : "text-text-secondary hover:text-foreground",
              )}
            >
              {LOGBOOK_COPY.result[value === "" ? "all" : value]}
            </button>
          ))}
        </div>
      </div>
      {!atLeast("md") ? (
        <Button
          variant="outline"
          className="min-h-10 self-start"
          aria-expanded={more}
          onClick={() => setMore(!more)}
        >
          {more ? "Fewer filters" : "More filters"}
          <ChevronDown className={more ? "rotate-180" : ""} aria-hidden />
        </Button>
      ) : null}
      <div className={cn("flex flex-wrap items-center gap-2", !showMore && "hidden")}>
        <MultiSelect
          label="Prompt version"
          value={filters.prompt_version_ids}
          onChange={(v) => set("prompt_version_ids", v)}
          choices={(options?.prompt_versions ?? []).map((v) => ({
            value: v.id,
            label: `Version ${v.version}`,
          }))}
        />
        <MultiSelect
          label="Experiment"
          value={filters.experiment_ids}
          onChange={(v) => set("experiment_ids", v)}
          choices={(options?.experiments ?? []).map((e) => ({
            value: e.id,
            label: e.name,
            hint: `${versionName(e.prompt_version)} · config ${shortHash(e.config_hash)}${
              sameConfiguration(options?.experiments ?? [], e.id, (x) => x.config_hash).length
                ? " (same as others)"
                : ""
            } · ${new Date(e.created_at).toLocaleString()}`,
          }))}
        />
        <MultiSelect
          label="Model"
          value={filters.models}
          onChange={(v) => set("models", v)}
          choices={(options?.models ?? []).map((m) => ({ value: m, label: m }))}
        />
        <MultiSelect
          label="Provider"
          value={filters.providers}
          onChange={(v) => set("providers", v)}
          choices={(options?.providers ?? []).map((m) => ({ value: m, label: m }))}
        />
        <MultiSelect
          label="Source"
          value={filters.sources}
          onChange={(v) => set("sources", v)}
          choices={SOURCES}
        />
        <MultiSelect
          label="Category"
          value={filters.categories}
          onChange={(v) => set("categories", v)}
          choices={(options?.categories ?? []).map((m) => ({ value: m, label: m }))}
        />
        <MultiSelect
          label="Failed check"
          value={filters.failed_checks}
          onChange={(v) => set("failed_checks", v)}
          choices={(options?.checks ?? []).map((m) => ({ value: m, label: m.replaceAll("_", " "), hint: m }))}
        />
        <MultiSelect
          label="Call"
          value={filters.statuses}
          onChange={(v) => set("statuses", v)}
          choices={STATUSES}
        />
        <label className="text-text-secondary flex items-center gap-1.5 text-sm">
          From
          <Input
            type="date"
            value={filters.date_from}
            onChange={(e) => set("date_from", e.target.value)}
            className="h-10 w-40 sm:h-9"
          />
        </label>
        <label className="text-text-secondary flex items-center gap-1.5 text-sm">
          To
          <Input
            type="date"
            value={filters.date_to}
            onChange={(e) => set("date_to", e.target.value)}
            className="h-10 w-40 sm:h-9"
          />
        </label>
      </div>
      {chips.length > 0 || total !== undefined ? (
        <div className="flex flex-wrap items-center gap-2">
          {chips.map((chip) => (
            <button
              key={chip.key}
              type="button"
              onClick={chip.remove}
              aria-label={`Remove filter ${chip.label}`}
              className="bg-lagoon-soft text-lagoon-strong hover:bg-lagoon/15 inline-flex items-center gap-1 rounded-full py-1 pr-2 pl-3 text-xs font-medium"
            >
              {chip.label}
              <X className="size-3.5" />
            </button>
          ))}
          {active > 0 ? (
            <Button variant="ghost" size="sm" onClick={() => onChange(EMPTY_FILTERS)}>
              {LOGBOOK_COPY.clear}
            </Button>
          ) : null}
          {total !== undefined ? (
            <span className="text-text-secondary ml-auto text-sm" aria-live="polite">
              {total.toLocaleString()} {total === 1 ? "answer" : "answers"}
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
