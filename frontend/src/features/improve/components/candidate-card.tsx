/** One candidate prompt: its strategy, why each change was made, the diff, and its score. */
import { StatusBadge } from "@/components/common/status-badge"
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { CandidateOut } from "@/lib/api/types"

import { IMPROVE_COPY } from "../copy"

export const percent = (value: number | null | undefined) =>
  value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`

function DiffLine({ line }: { line: string }) {
  const tone =
    line.startsWith("+") && !line.startsWith("+++")
      ? "text-success"
      : line.startsWith("-") && !line.startsWith("---")
        ? "text-destructive"
        : "text-muted-foreground"
  return <div className={tone}>{line || " "}</div>
}

export function CandidateCard({ candidate, baseline }: { candidate: CandidateOut; baseline: number | null }) {
  return (
    <Card size="sm" className="shadow-none">
      <CardHeader>
        <CardTitle className="capitalize">{candidate.strategy}</CardTitle>
        <CardAction>
          <StatusBadge
            tone={
              candidate.outcome === "better" || candidate.outcome === "accepted"
                ? "success"
                : candidate.outcome === "pending"
                  ? "info"
                  : "neutral"
            }
          >
            {IMPROVE_COPY.outcome[candidate.outcome]}
          </StatusBadge>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        <p>
          {IMPROVE_COPY.optimizeScore}:{" "}
          <span className="font-medium">{percent(candidate.optimize_quality)}</span>{" "}
          <span className="text-muted-foreground">
            ({IMPROVE_COPY.current} {percent(baseline)})
          </span>
        </p>
        <ul className="list-disc pl-5">
          {candidate.change_reasons.map((reason, index) => (
            <li key={index}>{String(reason)}</li>
          ))}
        </ul>
        <pre className="bg-card ring-border max-h-72 overflow-auto rounded-lg p-2 font-mono text-xs whitespace-pre-wrap ring-1">
          {candidate.diff.split("\n").map((line, index) => (
            <DiffLine key={index} line={line} />
          ))}
        </pre>
      </CardContent>
    </Card>
  )
}
