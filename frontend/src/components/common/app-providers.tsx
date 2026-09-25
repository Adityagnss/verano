/**
 * Client-side providers for the whole app: TanStack Query (cached server state; 4xx
 * answers are not retried because they won't change on retry) and the toast host.
 */
"use client"

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { type ReactNode, useState } from "react"

import { Toaster } from "@/components/ui/sonner"
import { ApiError } from "@/lib/api/client"

const MAX_RETRIES = 2
const STALE_MS = 30_000

function shouldRetry(failures: number, error: unknown): boolean {
  const clientError = error instanceof ApiError && error.status < 500
  return !clientError && failures < MAX_RETRIES
}

export function AppProviders({ children }: { children: ReactNode }) {
  const [client] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: shouldRetry, staleTime: STALE_MS } } }),
  )
  return (
    <QueryClientProvider client={client}>
      {children}
      <Toaster theme="dark" position="top-right" />
    </QueryClientProvider>
  )
}
