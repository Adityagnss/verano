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

import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/select"

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

type Filters = {
  provider: string
  price: "any" | "free" | "paid" | "unknown"
  context: number
  json: boolean
  selectedOnly: boolean
  sort: "name" | "cheapest" | "context"
}
const NO_FILTERS: Filters = {
  provider: "",
  price: "any",
  context: 0,
  json: false,
  selectedOnly: false,
  sort: "name",
}
const CONTEXT_STEPS = [0, 32_000, 128_000, 1_000_000]

function priceKind(model: ModelProfileOut): "free" | "paid" | "unknown" {
  if (!model.price_known) return "unknown"
  return model.price_source === "free" ? "free" : "paid"
}

function cost(model: ModelProfileOut): number {
  return model.price_known
    ? Number(model.input_price_per_mtok) + Number(model.output_price_per_mtok)
    : Infinity
}

function applyFilters(models: ModelProfileOut[], filters: Filters, selected: Set<string>): ModelProfileOut[] {
  const kept = models.filter(
    (model) =>
      (!filters.provider || model.provider === filters.provider) &&
      (filters.price === "any" || priceKind(model) === filters.price) &&
      (model.context_window ?? 0) >= filters.context &&
      (!filters.json || model.supports_json_mode) &&
      (!filters.selectedOnly || selected.has(model.id)),
  )
  const order = {
    name: (a: ModelProfileOut, b: ModelProfileOut) => a.display_name.localeCompare(b.display_name),
    cheapest: (a: ModelProfileOut, b: ModelProfileOut) =>
      cost(a) - cost(b) || a.display_name.localeCompare(b.display_name),
    context: (a: ModelProfileOut, b: ModelProfileOut) => (b.context_window ?? 0) - (a.context_window ?? 0),
  }[filters.sort]
  return [...kept].sort(order)
}

function FilterField({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-[9rem] flex-1 flex-col gap-1">
      <Label htmlFor={id} className="text-text-secondary text-xs">
        {label}
      </Label>
      {children}
    </div>
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
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  const patch = (change: Partial<Filters>) => setFilters((current) => ({ ...current, ...change }))
  const filtered = useMemo(() => applyFilters(models, filters, selected), [models, filters, selected])
  const providers = useMemo(() => [...new Set(models.map((model) => model.provider))].sort(), [models])
  const filtering = JSON.stringify(filters) !== JSON.stringify(NO_FILTERS)
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
      data: filtered,
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
      <div className="bg-subtle ring-border flex flex-col gap-3 rounded-lg p-3 ring-1">
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={KEYS_COPY.search}
          className="bg-card w-full sm:max-w-sm"
          aria-label={KEYS_COPY.search}
        />
        <div className="flex flex-wrap items-end gap-3">
          <FilterField id="f-provider" label={KEYS_COPY.filters.provider}>
            <NativeSelect
              id="f-provider"
              value={filters.provider}
              onChange={(event) => patch({ provider: event.target.value })}
            >
              <option value="">{KEYS_COPY.filters.allProviders}</option>
              {providers.map((provider) => (
                <option key={provider} value={provider}>
                  {providerNames[provider] ?? provider}
                </option>
              ))}
            </NativeSelect>
          </FilterField>
          <FilterField id="f-price" label={KEYS_COPY.filters.price}>
            <NativeSelect
              id="f-price"
              value={filters.price}
              onChange={(event) => patch({ price: event.target.value as Filters["price"] })}
            >
              <option value="any">{KEYS_COPY.filters.anyPrice}</option>
              <option value="free">{KEYS_COPY.filters.free}</option>
              <option value="paid">{KEYS_COPY.filters.paid}</option>
              <option value="unknown">{KEYS_COPY.filters.unknown}</option>
            </NativeSelect>
          </FilterField>
          <FilterField id="f-context" label={KEYS_COPY.filters.context}>
            <NativeSelect
              id="f-context"
              value={filters.context}
              onChange={(event) => patch({ context: Number(event.target.value) })}
            >
              {CONTEXT_STEPS.map((size) => (
                <option key={size} value={size}>
                  {size ? `${formatTokens(size)}+` : KEYS_COPY.filters.anyContext}
                </option>
              ))}
            </NativeSelect>
          </FilterField>
          <FilterField id="f-sort" label={KEYS_COPY.filters.sort}>
            <NativeSelect
              id="f-sort"
              value={filters.sort}
              onChange={(event) => patch({ sort: event.target.value as Filters["sort"] })}
            >
              {(Object.keys(KEYS_COPY.filters.sorts) as Filters["sort"][]).map((key) => (
                <option key={key} value={key}>
                  {KEYS_COPY.filters.sorts[key]}
                </option>
              ))}
            </NativeSelect>
          </FilterField>
        </div>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
          <label className="flex items-center gap-2">
            <Checkbox
              checked={filters.json}
              aria-label={KEYS_COPY.filters.json}
              onCheckedChange={(checked) => patch({ json: checked })}
            />
            {KEYS_COPY.filters.json}
          </label>
          <label className="flex items-center gap-2">
            <Checkbox
              checked={filters.selectedOnly}
              aria-label={KEYS_COPY.filters.selectedOnly}
              onCheckedChange={(checked) => patch({ selectedOnly: checked })}
            />
            {KEYS_COPY.filters.selectedOnly}
          </label>
          <span className="text-text-secondary ml-auto" aria-live="polite">
            {KEYS_COPY.filters.shown(rows.length, models.length)}
          </span>
          {filtering || query ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setFilters(NO_FILTERS)
                setQuery("")
              }}
            >
              {KEYS_COPY.filters.clear}
            </Button>
          ) : null}
        </div>
      </div>
      <div className="border-border bg-card overflow-hidden rounded-lg border text-sm">
        <div className={`${GRID} bg-subtle text-text-secondary h-10 text-xs font-medium`}>
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
          {rows.length === 0 ? (
            <p className="text-text-secondary px-4 py-10 text-center text-sm">{KEYS_COPY.filters.none}</p>
          ) : null}
          <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
            {virtualizer.getVirtualItems().map((item) => {
              const row = rows[item.index]
              return (
                <div
                  key={row.id}
                  role="listitem"
                  className={`${GRID} border-border hover:bg-subtle/60 absolute inset-x-0 border-b transition-colors`}
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
