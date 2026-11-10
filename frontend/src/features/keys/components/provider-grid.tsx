/** Provider cards: one per provider in the catalog, each with its "Add key" action. */
import { Plus } from "lucide-react"

import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import type { CredentialOut, ProviderOut } from "@/lib/api/types"

import { KEYS_COPY } from "../copy"

function initials(name: string): string {
  const capitals = name.replace(/\(.*\)/, "").match(/[A-Z]/g) ?? []
  return capitals.length >= 2 ? capitals.slice(0, 2).join("") : name.slice(0, 2)
}

export function ProviderGrid({
  providers,
  credentials = [],
  onAdd,
}: {
  providers: ProviderOut[]
  credentials?: CredentialOut[]
  onAdd: (provider: ProviderOut) => void
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {providers.map((provider) => {
        const mine = credentials.filter((c) => c.provider === provider.name)
        const models = mine.reduce((sum, c) => sum + c.model_count, 0)
        return (
          <div
            key={provider.name}
            data-slot="card"
            className="bg-card ring-border hover:ring-lagoon/40 flex items-center gap-3 rounded-xl p-3 ring-1 transition-shadow hover:shadow-md"
          >
            <span className="from-lagoon-soft to-subtle text-lagoon-strong ring-lagoon/15 flex size-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br text-sm font-bold ring-1">
              {initials(provider.display_name)}
            </span>
            <div className="flex min-w-0 flex-1 flex-col items-start gap-0.5">
              <span className="w-full truncate text-sm font-semibold">{provider.display_name}</span>
              {mine.length ? (
                <StatusBadge tone="success">{KEYS_COPY.connected(models)}</StatusBadge>
              ) : provider.free ? (
                <StatusBadge tone="success">{KEYS_COPY.free}</StatusBadge>
              ) : (
                <span className="text-text-muted text-xs">{KEYS_COPY.notConnected}</span>
              )}
            </div>
            <Button variant="outline" className="min-h-10" onClick={() => onAdd(provider)}>
              <Plus />
              {provider.requires_key ? KEYS_COPY.addKey : KEYS_COPY.connect}
            </Button>
          </div>
        )
      })}
    </div>
  )
}
