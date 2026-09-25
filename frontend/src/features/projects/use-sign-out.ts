/** Sign-out for the project screens: ends the server session, clears cached data, leaves. */
"use client"

import { useMutation, useQueryClient } from "@tanstack/react-query"

import { endSession } from "@/lib/auth/session"

export function useSignOutAndLeave(leave: () => void) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: endSession,
    onSuccess: () => {
      queryClient.clear()
      leave()
    },
  })
}
