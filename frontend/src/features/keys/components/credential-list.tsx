/**
 * The project's saved keys: provider, name, last four characters, whether the provider
 * accepted it, and how many chat models it reaches, with refresh and remove actions.
 * Removing asks for confirmation first.
 */
"use client"

import { RefreshCw, Trash2 } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import type { CredentialOut } from "@/lib/api/types"

import { KEYS_COPY } from "../copy"
import { useRefreshModels, useRemoveCredential } from "../hooks"

type Props = { projectId: string; credentials: CredentialOut[]; providerNames: Record<string, string> }

export function CredentialList({ projectId, credentials, providerNames }: Props) {
  const refresh = useRefreshModels(projectId)
  const remove = useRemoveCredential(projectId)
  const [removing, setRemoving] = useState<CredentialOut | null>(null)

  if (credentials.length === 0) {
    return <EmptyState title={KEYS_COPY.noKeysTitle} description={KEYS_COPY.noKeysDescription} />
  }

  async function refreshModels(id: string) {
    const credential = await refresh.mutateAsync(id)
    toast.success(KEYS_COPY.refreshed(credential.model_count))
  }

  async function confirmRemove() {
    if (!removing) return
    await remove.mutateAsync(removing.id)
    setRemoving(null)
    toast.success(KEYS_COPY.removed)
  }

  return (
    <div className="flex flex-col gap-2">
      <ErrorMessage error={refresh.error} />
      <ul className="border-border divide-border divide-y rounded-lg border">
        {credentials.map((credential) => (
          <li key={credential.id} className="flex items-center gap-4 px-4 py-3 text-sm">
            <span className="font-medium">{providerNames[credential.provider] ?? credential.provider}</span>
            {credential.label ? <span className="text-muted-foreground">{credential.label}</span> : null}
            {credential.key_last4 ? (
              <span className="text-muted-foreground font-mono">••••{credential.key_last4}</span>
            ) : null}
            <Badge variant={credential.status === "valid" ? "secondary" : "destructive"}>
              {credential.status === "valid" ? KEYS_COPY.valid : KEYS_COPY.invalid}
            </Badge>
            <span className="text-muted-foreground">{KEYS_COPY.models(credential.model_count)}</span>
            <div className="ml-auto flex gap-1">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void refreshModels(credential.id).catch(() => undefined)}
                disabled={refresh.isPending}
              >
                <RefreshCw />
                {KEYS_COPY.refresh}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setRemoving(credential)}
                aria-label={KEYS_COPY.remove}
              >
                <Trash2 />
              </Button>
            </div>
          </li>
        ))}
      </ul>
      <Dialog open={removing !== null} onOpenChange={(open) => (open ? undefined : setRemoving(null))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{KEYS_COPY.removeTitle}</DialogTitle>
            <DialogDescription>{KEYS_COPY.removeDescription}</DialogDescription>
          </DialogHeader>
          <ErrorMessage error={remove.error} />
          <DialogFooter>
            <Button
              variant="destructive"
              onClick={() => void confirmRemove().catch(() => undefined)}
              disabled={remove.isPending}
            >
              {KEYS_COPY.remove}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
