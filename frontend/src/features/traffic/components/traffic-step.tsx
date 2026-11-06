/** Real traffic: the list, live scores, alerts and how to connect an app. */
"use client"

import { useState } from "react"

import { Button } from "@/components/ui/button"

import { TRAFFIC_COPY as C } from "../copy"
import { AlertsPanel } from "./alerts-panel"
import { ConnectPanel } from "./connect-panel"
import { ScoringPanel } from "./scoring-panel"
import { TrafficList } from "./traffic-list"

const TABS = ["list", "scoring", "alerts", "connect"] as const

export function TrafficStep({ projectId }: { projectId: string }) {
  const [tab, setTab] = useState<(typeof TABS)[number]>("list")
  return (
    <div className="flex flex-col gap-6">
      <div role="tablist" className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <Button
            key={t}
            role="tab"
            aria-selected={tab === t}
            variant={tab === t ? "default" : "outline"}
            onClick={() => setTab(t)}
          >
            {C.tabs[t]}
          </Button>
        ))}
      </div>
      {tab === "list" ? <TrafficList projectId={projectId} /> : null}
      {tab === "scoring" ? <ScoringPanel projectId={projectId} /> : null}
      {tab === "alerts" ? <AlertsPanel projectId={projectId} /> : null}
      {tab === "connect" ? <ConnectPanel projectId={projectId} /> : null}
    </div>
  )
}
