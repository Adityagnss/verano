/**
 * The discovered models with a checkbox each. Search uses TanStack Table (v9, with only the
 * global-filter feature registered) and rendering uses TanStack Virtual, so a provider
 * exposing hundreds of models stays fast: only the visible rows are in the DOM. Prices are per million tokens; an unknown price is
 * shown as unknown (in amber), never as $0, and local models as free.
 */
"use client"

import {
  columnFilteringFeature,
  createColumnHelper,
  createFilteredRowModel,
  filterFn_includesString,
  globalFilteringFeature,
  tableFeatures,
  useTable,
} from "@tanstack/react-table"
import { useVirtualizer } from "@tanstack/react-virtual"
import { useMemo, useRef, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import type { ModelProfileOut } from "@/lib/api/types"
import { formatPricePair, formatTokens } from "@/lib/format"

import { KEYS_COPY } from "../copy"

const ROW_HEIGHT = 52
const SEARCHABLE_COLUMNS = new Set(["model", "provider"])

const features = tableFeatures({
  columnFilteringFeature,
  globalFilteringFeature,
  filteredRowModel: createFilteredRowModel(),
  filterFns: { includesString: filterFn_includesString },
})
const helper = createColumnHelper<typeof features, ModelProfileOut>()
const GRID =
  "grid grid-cols-[2.5rem_minmax(0,2.4fr)_minmax(0,1fr)_5.5rem_minmax(0,1.4fr)] items-center gap-3 px-3"

function Price({ model }: { model: ModelProfileOut }) {
  if (!model.price_known) return <span className="text-warning">{KEYS_COPY.priceUnknown}</span>
  if (model.price_source === "free") return <span className="text-success">{KEYS_COPY.priceFree}</span>
  return (
    <span title={KEYS_COPY.perMillion}>
      {formatPricePair(model.input_price_per_mtok, model.output_price_per_mtok)}
    </span>
  )
}

type Props = {
  models: ModelProfileOut[]
  providerNames: Record<string, string>
  selected: Set<string>
  onToggle: (id: string, checked: boolean) => void
}

export function ModelTable({ models, providerNames, selected, onToggle }: Props) {
  const [query, setQuery] = useState("")
  const columns = useMemo(
    () =>
      helper.columns([
        helper.display({
          id: "select",
          cell: ({ row }) => (
            <Checkbox
              checked={selected.has(row.original.id)}
              onCheckedChange={(checked) => onToggle(row.original.id, checked)}
              aria-label={row.original.display_name}
            />
          ),
        }),
        helper.accessor((model) => `${model.display_name} ${model.model_name}`, {
          id: "model",
          header: KEYS_COPY.columns.model,
          cell: ({ row }) => (
            <div className="min-w-0">
              <div className="flex items-center gap-2 truncate font-medium">
                {row.original.display_name}
                {row.original.supports_json_mode ? (
                  <Badge variant="outline">{KEYS_COPY.jsonMode}</Badge>
                ) : null}
              </div>
              <div className="text-muted-foreground truncate font-mono text-xs">
                {row.original.model_name}
              </div>
            </div>
          ),
        }),
        helper.accessor((model) => providerNames[model.provider] ?? model.provider, {
          id: "provider",
          header: KEYS_COPY.columns.provider,
        }),
        helper.display({
          id: "context",
          header: KEYS_COPY.columns.context,
          cell: ({ row }) => formatTokens(row.original.context_window),
        }),
        helper.display({
          id: "price",
          header: KEYS_COPY.columns.price,
          cell: ({ row }) => <Price model={row.original} />,
        }),
      ]),
    [selected, onToggle, providerNames],
  )
  const table = useTable(
    {
      features,
      columns,
      data: models,
      state: { globalFilter: query },
      onGlobalFilterChange: (updater) => setQuery(typeof updater === "function" ? updater(query) : updater),
      globalFilterFn: "includesString",
      getColumnCanGlobalFilter: (column) => SEARCHABLE_COLUMNS.has(column.id),
    },
    (state) => ({ globalFilter: state.globalFilter }),
  )
  const rows = table.getRowModel().rows
  const scroller = useRef<HTMLDivElement>(null)
  // eslint-disable-next-line react-hooks/incompatible-library -- TanStack Virtual; React Compiler is not enabled
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => ROW_HEIGHT,
    getItemKey: (index) => rows[index].id,
    overscan: 8,
  })

  return (
    <div className="flex flex-col gap-3">
      <Input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={KEYS_COPY.search}
        className="max-w-sm"
        aria-label={KEYS_COPY.search}
      />
      <div className="border-border overflow-hidden rounded-lg border text-sm">
        <div className={`${GRID} bg-secondary text-muted-foreground h-10 text-xs font-medium`}>
          {table.getHeaderGroups()[0].headers.map((header) => (
            <div key={header.id}>
              <table.FlexRender header={header} />
            </div>
          ))}
        </div>
        <div
          ref={scroller}
          className="max-h-[28rem] overflow-y-auto"
          role="list"
          aria-label={KEYS_COPY.modelsHeading}
        >
          <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
            {virtualizer.getVirtualItems().map((item) => {
              const row = rows[item.index]
              return (
                <div
                  key={row.id}
                  role="listitem"
                  className={`${GRID} border-border absolute inset-x-0 border-b`}
                  style={{ height: item.size, transform: `translateY(${item.start}px)` }}
                >
                  {row.getAllCells().map((cell) => (
                    <div key={cell.id} className="min-w-0">
                      <table.FlexRender cell={cell} />
                    </div>
                  ))}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
