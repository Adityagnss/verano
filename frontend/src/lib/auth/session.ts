/**
 * The browser session: the access token lives only in this module's memory, never in
 * localStorage or a readable cookie. The refresh token is an httpOnly cookie the browser
 * sends only to /api/v1/auth/refresh, so page scripts can never read it.
 *
 * Refresh tokens rotate on every use and reuse revokes the whole chain, so two refreshes
 * racing with the same cookie would sign the user out. Refresh is therefore single-flight
 * within a tab (one shared promise) and serialized across tabs with the Web Locks API:
 * a second tab waits, then refreshes with the cookie the first tab already rotated.
 */
import type { SessionOut, UserOut } from "@/lib/api/types"

export type SessionStatus = "unknown" | "signed-in" | "signed-out"
export type SessionSnapshot = { status: SessionStatus; user: UserOut | null }

export const REFRESH_PATH = "/api/v1/auth/refresh"
const LOCK_NAME = "verano-session-refresh"

let token: string | null = null
let snapshot: SessionSnapshot = { status: "unknown", user: null }
let inflight: Promise<boolean> | null = null
const listeners = new Set<() => void>()

export function accessToken(): string | null {
  return token
}

export function setSession(session: SessionOut | null): void {
  token = session?.access_token ?? null
  snapshot = session ? { status: "signed-in", user: session.user } : { status: "signed-out", user: null }
  listeners.forEach((listener) => listener())
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getSnapshot(): SessionSnapshot {
  return snapshot
}

const SERVER_SNAPSHOT: SessionSnapshot = { status: "unknown", user: null }

export function getServerSnapshot(): SessionSnapshot {
  return SERVER_SNAPSHOT
}

async function rotate(): Promise<boolean> {
  const response = await fetch(REFRESH_PATH, { method: "POST", credentials: "same-origin" })
  setSession(response.ok ? ((await response.json()) as SessionOut) : null)
  return response.ok
}

function serialized(task: () => Promise<boolean>): Promise<boolean> {
  const locks = typeof navigator !== "undefined" ? navigator.locks : undefined
  return locks ? locks.request(LOCK_NAME, task).then((granted) => granted) : task()
}

export function refreshSession(): Promise<boolean> {
  inflight ??= serialized(rotate).finally(() => {
    inflight = null
  })
  return inflight
}

export async function endSession(): Promise<void> {
  await fetch(REFRESH_PATH, { method: "DELETE", credentials: "same-origin" })
  setSession(null)
}
