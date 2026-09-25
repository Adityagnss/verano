/** Shows an error in words that say what to do; API errors already carry such a message. */
import { CircleAlert } from "lucide-react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { ApiError } from "@/lib/api/client"

const FALLBACK = "Something went wrong. Try again in a moment."

export function ErrorMessage({ error }: { error: unknown }) {
  if (!error) return null
  const message = error instanceof ApiError || error instanceof Error ? error.message : FALLBACK
  return (
    <Alert variant="destructive" role="alert">
      <CircleAlert />
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  )
}
