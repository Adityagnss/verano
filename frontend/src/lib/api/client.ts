/**
 * The typed API client (openapi-fetch over the generated `paths`). Requests go to the
 * same origin; Next.js forwards /api/* to the backend, which keeps the refresh cookie
 * first-party. The access token is attached to every request; a 401 triggers one session
 * refresh and one retry. Errors come back in the backend's single error format and are
 * raised as `ApiError`, whose message is already written for the user.
 */
import createClient from "openapi-fetch"

import { accessToken, refreshSession } from "@/lib/auth/session"

import type { paths } from "./schema"

export const api = createClient<paths>({ baseUrl: "", credentials: "same-origin" })

api.use({
  onRequest({ request }) {
    const current = accessToken()
    if (current) request.headers.set("Authorization", `Bearer ${current}`)
    return request
  },
})

type ErrorBody = { error?: { code?: string; message?: string; details?: unknown } }

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: unknown,
  ) {
    super(message)
  }
}

const FALLBACK_MESSAGE = "Something went wrong. Try again in a moment."

function toApiError(response: Response, body: unknown): ApiError {
  const error = (body as ErrorBody | undefined)?.error
  return new ApiError(
    response.status,
    error?.code ?? "unknown",
    error?.message ?? FALLBACK_MESSAGE,
    error?.details,
  )
}

type Result<T> = { data?: T; error?: unknown; response: Response }

export async function call<T>(send: () => Promise<Result<T>>): Promise<T> {
  let result = await send()
  if (result.response.status === 401 && (await refreshSession())) result = await send()
  if (!result.response.ok) throw toApiError(result.response, result.error)
  return result.data as T
}
