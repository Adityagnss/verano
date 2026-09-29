/**
 * The Logbook: one place that records everything, as tabs over the same records. Answers is
 * the spreadsheet of model answers, Analysis draws charts for whatever the filters select
 * (the filters are shared between the two), and Model calls lists every call the app made.
 */
"use client"

import { BarChart3, ListTree, Table2 } from "lucide-react"
import { useState } from "react"

import { cn } from "@/lib/utils"

import { LOGBOOK_COPY } from "../copy"
import { type AnswerFilters, EMPTY_FILTERS } from "../domain"
import { type Paging, useLogOptions } from "../hooks"
import { AnalysisTab } from "./analysis-tab"
import { AnswersTab } from "./answers-tab"
import { CallsTab } from "./calls-tab"

type Tab = "answers" | "analysis" | "calls"
const TABS: { key: Tab; icon: typeof Table2 }[] = [
  { key: "answers", icon: Table2 },
  { key: "analysis", icon: BarChart3 },
  { key: "calls", icon: ListTree },
]

export function LogbookPage({ projectId }: { projectId: string }) {
  const [tab, setTab] = useState<Tab>("answers")
  const [filters, setFilters] = useState<AnswerFilters>(EMPTY_FILTERS)
  const [paging, setPaging] = useState<Paging>({ sort: "time", order: "desc", offset: 0, limit: 50 })
  const options = useLogOptions(projectId)
  return (
    <div className="mx-auto flex w-full max-w-[112rem] flex-col gap-5">
      <header className="border-border flex flex-col gap-2 border-b pb-5">
        <p className="text-text-secondary text-sm">Tools</p>
        <h2 className="text-2xl leading-tight font-semibold sm:text-[1.95rem]">{LOGBOOK_COPY.title}</h2>
        <p className="text-text-secondary max-w-[56rem] text-[0.95rem] leading-relaxed">
          {LOGBOOK_COPY.subtitle}
        </p>
      </header>
      <div role="tablist" aria-label="Logbook views" className="flex flex-wrap gap-2">
        {TABS.map(({ key, icon: Icon }) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={cn(
              "flex items-center gap-2 rounded-xl px-4 py-2.5 text-left text-sm ring-1 transition-colors",
              tab === key
                ? "bg-lagoon-soft ring-lagoon/30 text-lagoon-strong"
                : "bg-card ring-border hover:bg-subtle",
            )}
          >
            <Icon className="size-4 shrink-0" />
            <span className="flex flex-col leading-tight">
              <span className="font-semibold">{LOGBOOK_COPY.tabs[key]}</span>
              <span className="text-text-muted hidden text-xs font-normal sm:inline">
                {LOGBOOK_COPY.tabHints[key]}
              </span>
            </span>
          </button>
        ))}
      </div>
      {tab === "answers" ? (
        <AnswersTab
          projectId={projectId}
          options={options.data}
          filters={filters}
          onFilters={setFilters}
          paging={paging}
          onPaging={setPaging}
        />
      ) : null}
      {tab === "analysis" ? (
        <AnalysisTab projectId={projectId} options={options.data} filters={filters} onFilters={setFilters} />
      ) : null}
      {tab === "calls" ? <CallsTab projectId={projectId} options={options.data} /> : null}
    </div>
  )
}
