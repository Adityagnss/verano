/** A clear banner when the test cases are too few to trust the results, with the way to add more. */
"use client"

import { CircleAlert } from "lucide-react"
import Link from "next/link"

import { useCurrentVersion } from "@/features/tests/hooks"

export function DatasetWarnings({ projectId }: { projectId: string }) {
  const version = useCurrentVersion(projectId)
  const warnings = version.data?.warnings ?? []
  if (warnings.length === 0) return null
  return (
    <div className="bg-marigold-soft text-marigold-strong ring-marigold/30 flex items-start gap-2 rounded-xl p-4 text-sm ring-1">
      <CircleAlert className="mt-0.5 size-4 shrink-0" />
      <div className="flex-1">
        <p className="font-semibold">
          With {version.data?.item_count ?? 0} test cases these results can&apos;t be fully trusted.
        </p>
        {warnings.map((warning) => (
          <p key={warning}>{warning}</p>
        ))}
      </div>
      <Link href={`/projects/${projectId}/tests`} className="font-medium whitespace-nowrap underline">
        Add more test cases →
      </Link>
    </div>
  )
}
