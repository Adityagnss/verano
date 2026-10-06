/** The Activity page's data: one request per period and time zone. */
"use client"

import { useQuery } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"

export function useActivity(days: number, tz: string) {
  return useQuery({
    queryKey: ["activity", days, tz],
    queryFn: () => call(() => api.GET("/api/v1/activity", { params: { query: { days, tz } } })),
  })
}
