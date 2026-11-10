/**
 * An empty screen that is an invitation: an icon, a title, one sentence about what goes here, and
 * one primary action. Built on the shadcn Empty component. Never leave a blank panel.
 *
 *   <EmptyState icon={FileText} title="No prompt yet" description="Write the instructions to test."
 *     action={<Button>Write your prompt</Button>} />
 */
import type { LucideIcon } from "lucide-react"
import type { ReactNode } from "react"

import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { cn } from "@/lib/utils"

export function EmptyState({
  title,
  description,
  action,
  icon: Icon,
  className,
}: {
  title: string
  description: string
  action?: ReactNode
  icon?: LucideIcon
  className?: string
}) {
  return (
    <Empty className={cn("border-border-strong bg-card border py-12", className)}>
      <EmptyHeader>
        {Icon ? (
          <EmptyMedia variant="icon" className="bg-lagoon-soft text-lagoon-strong size-10 rounded-xl">
            <Icon className="size-5" aria-hidden />
          </EmptyMedia>
        ) : null}
        <EmptyTitle className="text-base font-semibold">{title}</EmptyTitle>
        <EmptyDescription className="text-text-secondary">{description}</EmptyDescription>
      </EmptyHeader>
      {action ? <EmptyContent>{action}</EmptyContent> : null}
    </Empty>
  )
}
