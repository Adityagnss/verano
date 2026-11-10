/**
 * `ResponsiveTable`: a normal table from 768px up, and under 768px a stack of cards (one per row;
 * each cell becomes a "Label: value" line, the `primary` column is the card's title). Only one of
 * the two is in the page at a time, so tests and screen readers see no duplicates. For huge data
 * sets with sorting and virtualisation keep using TanStack Table directly.
 *
 *   <ResponsiveTable
 *     rows={models}
 *     rowKey={(m) => m.id}
 *     caption="Models and their cost"
 *     columns={[
 *       { id: "name", header: "Model", primary: true, cell: (m) => m.name },
 *       { id: "cost", header: "Cost", align: "right", cell: (m) => formatCost(m.cost) },
 *     ]}
 *   />
 */
"use client"

import type { ReactNode } from "react"

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { cn } from "@/lib/utils"

import { useBreakpoint } from "./use-breakpoint"

export type ResponsiveColumn<Row> = {
  id: string
  header: string
  cell: (row: Row) => ReactNode
  /** The card's title line on small screens (use for one column). */
  primary?: boolean
  align?: "left" | "right"
  /** Leave this column out of the cards. */
  hideOnCards?: boolean
}

export function ResponsiveTable<Row>({
  rows,
  columns,
  rowKey,
  caption,
  empty,
  className,
}: {
  rows: Row[]
  columns: ResponsiveColumn<Row>[]
  rowKey: (row: Row) => string
  /** Accessible name of the table. */
  caption: string
  /** Shown instead of the table when there are no rows. */
  empty?: ReactNode
  className?: string
}) {
  const { atLeast } = useBreakpoint()
  if (rows.length === 0 && empty) return <>{empty}</>

  if (!atLeast("md")) {
    const title = columns.find((column) => column.primary) ?? columns[0]
    return (
      <ul aria-label={caption} className={cn("flex flex-col gap-3", className)}>
        {rows.map((row) => (
          <li key={rowKey(row)} className="bg-card ring-border flex flex-col gap-2 rounded-xl p-4 ring-1">
            <div className="font-medium break-words">{title.cell(row)}</div>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              {columns
                .filter((column) => column !== title && !column.hideOnCards)
                .map((column) => (
                  <div key={column.id} className="col-span-2 grid grid-cols-subgrid">
                    <dt className="text-text-muted">{column.header}</dt>
                    <dd className="min-w-0 text-right break-words">{column.cell(row)}</dd>
                  </div>
                ))}
            </dl>
          </li>
        ))}
      </ul>
    )
  }

  return (
    <div className={cn("bg-card ring-border overflow-hidden rounded-xl ring-1", className)}>
      <Table aria-label={caption}>
        <TableHeader>
          <TableRow>
            {columns.map((column) => (
              <TableHead key={column.id} className={cn(column.align === "right" && "text-right")}>
                {column.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={rowKey(row)}>
              {columns.map((column) => (
                <TableCell key={column.id} className={cn(column.align === "right" && "text-right")}>
                  {column.cell(row)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
