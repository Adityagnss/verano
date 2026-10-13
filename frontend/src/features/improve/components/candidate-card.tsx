/** One candidate prompt: its strategy, why each change was made, the diff, and its score. */
import { toast } from "sonner"

import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
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

function PromptText({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <p className="text-muted-foreground text-xs font-medium">{label}</p>
      <pre className="bg-card ring-border max-h-72 overflow-auto rounded-lg p-2 font-mono text-xs whitespace-pre-wrap ring-1">
        {text}
      </pre>
    </div>
  )
}

export function CandidateCard({
  candidate,
  baseline,
  onSave,
  saving,
}: {
  candidate: CandidateOut
  baseline: number | null
  onSave: () => Promise<unknown>
  saving: boolean
}) {
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
            {candidate.outcome === "not_better" &&
            (candidate.verdict?.reason === "not_proven" || candidate.verdict?.reason === "too_few_cases")
              ? IMPROVE_COPY.outcome.not_proven
              : IMPROVE_COPY.outcome[candidate.outcome]}
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
        <details className="text-sm">
          <summary className="text-accent cursor-pointer">{IMPROVE_COPY.fullPrompt}</summary>
          <div className="mt-2 flex flex-col gap-2">
            {candidate.system_template ? (
              <PromptText label={IMPROVE_COPY.systemPrompt} text={candidate.system_template} />
            ) : null}
            {candidate.user_template ? (
              <PromptText label={IMPROVE_COPY.userPrompt} text={candidate.user_template} />
            ) : null}
          </div>
        </details>
        <Button
          variant="outline"
          disabled={saving}
          onClick={() =>
            void onSave()
              .then(() => toast.success(IMPROVE_COPY.saved))
              .catch(() => undefined)
          }
        >
          {IMPROVE_COPY.save}
        </Button>
        <pre className="bg-card ring-border max-h-72 overflow-auto rounded-lg p-2 font-mono text-xs whitespace-pre-wrap ring-1">
          {candidate.diff.split("\n").map((line, index) => (
            <DiffLine key={index} line={line} />
          ))}
        </pre>
      </CardContent>
    </Card>
  )
}
