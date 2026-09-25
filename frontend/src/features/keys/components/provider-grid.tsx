/** Provider cards: one per provider in the catalog, each with its "Add key" action. */
import { Plus } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardHeader, CardTitle } from "@/components/ui/card"
import type { ProviderOut } from "@/lib/api/types"

import { KEYS_COPY } from "../copy"

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
            <CardTitle className="flex items-center gap-2">
              {provider.display_name}
              {provider.free ? <Badge variant="secondary">{KEYS_COPY.free}</Badge> : null}
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
