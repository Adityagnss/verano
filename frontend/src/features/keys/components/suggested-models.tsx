/** Three models to start with (cheap, balanced, strong), picked from what the project's keys reach. */
"use client"

import { Button } from "@/components/ui/button"
import type { ModelProfileOut } from "@/lib/api/types"
import { formatPricePair } from "@/lib/format"

import { KEYS_COPY } from "../copy"
import { suggestModels } from "../domain"

export function SuggestedModels({
  models,
  selected,
  onUse,
}: {
  models: ModelProfileOut[]
  selected: Set<string>
  onUse: (ids: string[]) => void
}) {
  const suggestions = suggestModels(models)
  if (suggestions.length === 0) return null
  const ids = suggestions.map((s) => s.model.id)
  const using = ids.length === selected.size && ids.every((id) => selected.has(id))
  return (
    <div className="bg-subtle ring-border flex flex-col gap-3 rounded-lg p-4 ring-1">
      <div>
        <h3 className="text-sm font-semibold">{KEYS_COPY.suggestedHeading}</h3>
        <p className="text-text-muted text-xs">{KEYS_COPY.suggestedHint}</p>
      </div>
      <ul className="grid gap-2 sm:grid-cols-3">
        {suggestions.map(({ tier, model }) => (
          <li key={model.id} className="bg-card ring-border rounded-lg p-3 text-sm ring-1">
            <p className="text-text-muted text-xs font-medium">{KEYS_COPY.tier[tier]}</p>
            <p className="font-semibold">{model.display_name}</p>
            <p className="text-text-muted text-xs">
              {model.price_source === "free"
                ? KEYS_COPY.priceFree
                : KEYS_COPY.suggestedPerMillion(
                    formatPricePair(model.input_price_per_mtok, model.output_price_per_mtok),
                  )}
            </p>
          </li>
        ))}
      </ul>
      <Button variant="outline" className="self-start" disabled={using} onClick={() => onUse(ids)}>
        {KEYS_COPY.useSuggested}
      </Button>
    </div>
  )
}
