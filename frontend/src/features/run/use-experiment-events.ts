/**
 * Live progress of one run over Server-Sent Events (ADR 0037). The server sends an event whenever the run's numbers or
 * state change; each event refreshes the run's queries, so the screen follows the run without asking every second.
 * `EventSource` can't send the Authorization header, so this reads the stream with `fetch`. If the connection drops
 * it reconnects with a growing pause; the ordinary polling stays on as a fallback.
 */
"use client"

import { useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"

import { accessToken } from "@/lib/auth/session"

export type RunEvent = {
  stage: string
  status: "running" | "succeeded" | "failed"
  processed: number
  total: number | null
  message: string | null
}

const FIRST_PAUSE_MS = 1000
const LONGEST_PAUSE_MS = 15000

/** The `data:` payloads of the complete events in `buffer`, and what is left over of an incomplete one. */
export function parseEvents(buffer: string): { events: RunEvent[]; rest: string } {
  const blocks = buffer.split("\n\n")
  const rest = blocks.pop() ?? ""
  const events: RunEvent[] = []
  for (const block of blocks) {
    const line = block.split("\n").find((l) => l.startsWith("data: "))
    if (!line) continue
    try {
      events.push(JSON.parse(line.slice(6)) as RunEvent)
    } catch {
      // a damaged event is skipped; the next one carries the full state anyway
    }
  }
  return { events, rest }
}

export function useExperimentEvents(
  projectId: string,
  experimentId: string,
  enabled: boolean,
): RunEvent | null {
  const queryClient = useQueryClient()
  const [latest, setLatest] = useState<RunEvent | null>(null)

  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()
    const url = `/api/v1/projects/${projectId}/experiments/${experimentId}/events`

    async function run() {
      let pause = FIRST_PAUSE_MS
      while (!controller.signal.aborted) {
        try {
          const token = accessToken()
          const response = await fetch(url, {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
            credentials: "same-origin",
            signal: controller.signal,
          })
          if (!response.ok || !response.body) throw new Error("stream refused")
          pause = FIRST_PAUSE_MS
          const reader = response.body.getReader()
          const decoder = new TextDecoder()
          let buffer = ""
          for (;;) {
            const { done, value } = await reader.read()
            if (done) return // the run ended: the server closes the stream
            buffer += decoder.decode(value, { stream: true })
            const parsed = parseEvents(buffer)
            buffer = parsed.rest
            for (const event of parsed.events) {
              setLatest(event)
              void queryClient.invalidateQueries({ queryKey: ["projects", projectId, "experiments"] })
            }
          }
        } catch {
          if (controller.signal.aborted) return
        }
        await new Promise((resolve) => window.setTimeout(resolve, pause))
        pause = Math.min(pause * 2, LONGEST_PAUSE_MS)
      }
    }

    void run()
    return () => controller.abort()
  }, [projectId, experimentId, enabled, queryClient])

  return latest
}
