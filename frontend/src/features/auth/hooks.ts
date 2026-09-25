/**
 * Auth hooks: whether sign-up is open, and the sign-in / sign-up mutations. A
 * successful sign-in stores the access token in memory (the refresh cookie is set by the
 * server) and clears any cached data from a previous user.
 */
"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, call } from "@/lib/api/client"
import { setSession } from "@/lib/auth/session"

type Credentials = { email: string; password: string }

export function useAuthConfig() {
  return useQuery({
    queryKey: ["auth", "config"],
    queryFn: () => call(() => api.GET("/api/v1/auth/config")),
  })
}

export function useSignIn() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Credentials) => call(() => api.POST("/api/v1/auth/login", { body })),
    onSuccess: (session) => {
      queryClient.clear()
      setSession(session)
    },
  })
}

export function useSignUp() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Credentials & { name: string }) =>
      call(() => api.POST("/api/v1/auth/signup", { body })),
    onSuccess: (session) => {
      queryClient.clear()
      setSession(session)
    },
  })
}
