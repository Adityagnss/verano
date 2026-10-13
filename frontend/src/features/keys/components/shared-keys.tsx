/** Keys already added in the organization's other projects, usable here without typing them again. */
"use client"

import { toast } from "sonner"

import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"

import { KEYS_COPY } from "../copy"
import { useCopyKey, useSharedKeys } from "../hooks"

export function SharedKeys({
  projectId,
  providerNames,
}: {
  projectId: string
  providerNames: Record<string, string>
}) {
  const shared = useSharedKeys(projectId)
  const copy = useCopyKey(projectId)
  const items = shared.data ?? []
  if (items.length === 0) return null
  return (
    <div className="bg-subtle ring-border flex flex-col gap-2 rounded-lg p-4 ring-1">
      <h3 className="text-sm font-semibold">{KEYS_COPY.sharedHeading}</h3>
      <ul className="flex flex-col gap-2">
        {items.map((key) => (
          <li key={key.id} className="flex flex-wrap items-center gap-3 text-sm">
            <span className="font-medium">{providerNames[key.provider] ?? key.provider}</span>
            <span className="text-text-muted font-mono text-xs">····{key.key_last4 ?? ""}</span>
            <span className="text-text-muted text-xs">{KEYS_COPY.sharedFrom(key.project_name)}</span>
            <Button
              size="sm"
              variant="outline"
              className="ml-auto"
              disabled={copy.isPending}
              onClick={() =>
                void copy
                  .mutateAsync(key.id)
                  .then(() => toast.success(KEYS_COPY.sharedUse))
                  .catch(() => undefined)
              }
            >
              {KEYS_COPY.sharedUse}
            </Button>
          </li>
        ))}
      </ul>
      <ErrorMessage error={copy.error} />
    </div>
  )
}
