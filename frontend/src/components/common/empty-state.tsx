/** An empty screen that explains itself: one sentence about what goes here, and the action. */
import type { ReactNode } from "react"

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="border-border flex flex-col items-center gap-3 rounded-lg border border-dashed px-6 py-12 text-center">
      <h3 className="text-base font-medium">{title}</h3>
      <p className="text-muted-foreground max-w-md text-sm">{description}</p>
      {action}
    </div>
  )
}
