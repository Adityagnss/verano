/** React binding for the in-memory session store (lib/auth/session.ts). */
"use client"

import { useSyncExternalStore } from "react"

import { getServerSnapshot, getSnapshot, type SessionSnapshot, subscribe } from "./session"

export function useSession(): SessionSnapshot {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
}
