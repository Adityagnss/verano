/** The prompting notes (Markdown) that the Improve step also reads. */
"use client"

import { useQuery } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"

export function usePromptNotes() {
  return useQuery({
    queryKey: ["prompt-notes"],
    queryFn: async () => (await call(() => api.GET("/api/v1/prompt-notes"))).markdown,
    staleTime: Infinity,
  })
}
