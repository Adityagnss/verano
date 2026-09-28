/** One candidate prompt: its strategy, why each change was made, the diff, and its score. */
import { Badge } from "@/components/ui/badge"
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
    <Card size="sm">
      <CardHeader>
        <CardTitle className="capitalize">{candidate.strategy}</CardTitle>
        <CardAction>
          <Badge
            variant={
              candidate.outcome === "better" || candidate.outcome === "accepted" ? "default" : "secondary"
            }
          >
            {IMPROVE_COPY.outcome[candidate.outcome]}
          </Badge>
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
        <pre className="bg-secondary max-h-72 overflow-auto rounded-lg p-3 font-mono text-xs whitespace-pre-wrap">
          {candidate.diff.split("\n").map((line, index) => (
            <DiffLine key={index} line={line} />
          ))}
        </pre>
      </CardContent>
    </Card>
  )
}
