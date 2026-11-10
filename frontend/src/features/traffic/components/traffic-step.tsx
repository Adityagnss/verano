/** Live traffic: a guided path, then the list, live scores, alerts and how to connect an app. */
"use client"

import { useState } from "react"

import { PageIntro } from "@/components/common/page-intro"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ALL_PROJECT_PAGES } from "@/lib/nav"

import { TRAFFIC_COPY as C } from "../copy"
import { useRules, useTokens, useTraces } from "../hooks"
import { AlertsPanel } from "./alerts-panel"
import { Checklist, type ChecklistKey } from "./checklist"
import { ConnectPanel } from "./connect-panel"
import { ScoringPanel } from "./scoring-panel"
import { TrafficList } from "./traffic-list"

const TABS = ["list", "scoring", "alerts", "connect"] as const
type Tab = (typeof TABS)[number]
const PAGE = ALL_PROJECT_PAGES.find((p) => p.key === "traffic")!
const NO_FILTERS = { failed: false, low_rated: false, long: false, new_topic: false, unused: false, q: "" }
const TAB_OF: Record<ChecklistKey, Tab> = {
  connected: "connect",
  hasTraffic: "list",
  caseMade: "list",
  hasAlertRule: "alerts",
}

export function TrafficStep({ projectId }: { projectId: string }) {
  const [tab, setTab] = useState<Tab>("list")
  const tokens = useTokens(projectId)
  const traces = useTraces(projectId, NO_FILTERS)
  const rules = useRules(projectId)
  const rows = traces.data?.pages.flatMap((p) => p.items) ?? []
  const state = {
    connected: (tokens.data ?? []).some((t) => !t.revoked_at),
    hasTraffic: rows.length > 0,
    caseMade: rows.some((t) => t.case_made),
    hasAlertRule: (rules.data ?? []).length > 0,
  }
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <PageIntro
        storageKey="traffic"
        title={PAGE.label}
        what="Real questions from your users and your app's answers, kept in one place."
        whenToUse="your app is already live and you want tests that match what people really ask"
        youGet="test cases made from real traffic, live quality scores and an alert when quality drops"
        primaryAction={
          <Button size="lg" onClick={() => setTab("connect")}>
            Connect your app
          </Button>
        }
        learnMore="traffic"
        hasContent={state.hasTraffic}
      />
      <Checklist state={state} onOpen={(key) => setTab(TAB_OF[key])} />
      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
        <div className="overflow-x-auto">
          <TabsList>
            {TABS.map((t) => (
              <TabsTrigger key={t} value={t} className="min-h-10 px-3">
                {C.tabs[t]}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        <TabsContent value="list" className="pt-4">
          <TrafficList projectId={projectId} />
        </TabsContent>
        <TabsContent value="scoring" className="pt-4">
          <ScoringPanel projectId={projectId} />
        </TabsContent>
        <TabsContent value="alerts" className="pt-4">
          <AlertsPanel projectId={projectId} />
        </TabsContent>
        <TabsContent value="connect" className="pt-4">
          <ConnectPanel projectId={projectId} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
