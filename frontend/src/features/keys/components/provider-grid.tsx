/** Provider cards: one per provider in the catalog, each with its "Add key" action. */
import { Plus } from "lucide-react"

import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardHeader, CardTitle } from "@/components/ui/card"
import type { ProviderOut } from "@/lib/api/types"

import { KEYS_COPY } from "../copy"

function initials(name: string): string {
  const capitals = name.replace(/\(.*\)/, "").match(/[A-Z]/g) ?? []
  return capitals.length >= 2 ? capitals.slice(0, 2).join("") : name.slice(0, 2)
}

export function ProviderGrid({
  providers,
  onAdd,
}: {
  providers: ProviderOut[]
  onAdd: (provider: ProviderOut) => void
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {providers.map((provider) => (
        <Card key={provider.name} size="sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2.5">
              <span className="bg-subtle text-text-secondary ring-border flex size-8 shrink-0 items-center justify-center rounded-lg text-xs font-bold ring-1">
                {initials(provider.display_name)}
              </span>
              {provider.display_name}
              {provider.free ? <StatusBadge tone="success">{KEYS_COPY.free}</StatusBadge> : null}
            </CardTitle>
            <CardAction>
              <Button variant="outline" size="sm" onClick={() => onAdd(provider)}>
                <Plus />
                {provider.requires_key ? KEYS_COPY.addKey : KEYS_COPY.connect}
              </Button>
            </CardAction>
          </CardHeader>
        </Card>
      ))}
    </div>
  )
}
