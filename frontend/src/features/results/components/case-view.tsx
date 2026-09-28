/** One test case with every model's output side by side, its pass/fail and each evaluator's reason. */
import { Badge } from "@/components/ui/badge"
import type { CaseResultOut } from "@/lib/api/types"
import { cn } from "@/lib/utils"

import { RESULTS_COPY } from "../copy"

export function CaseView({ item }: { item: CaseResultOut }) {
  return (
    <article className="border-border flex flex-col gap-3 rounded-lg border p-4">
      <header className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{item.category}</Badge>
        <Badge variant="outline">{item.source}</Badge>
        {item.split ? <Badge variant="secondary">{item.split}</Badge> : null}
      </header>
      <pre className="bg-secondary rounded-lg p-3 font-mono text-xs whitespace-pre-wrap">
        {Object.entries(item.inputs)
          .map(([key, value]) => `${key}: ${String(value)}`)
          .join("\n")}
      </pre>
      {item.expected_output ? (
        <p className="text-sm">
          <span className="text-muted-foreground">{RESULTS_COPY.expected}: </span>
          <span className="font-mono">{item.expected_output}</span>
        </p>
      ) : null}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {item.outputs.map((o) => (
          <div
            key={o.test_case_run_id}
            className={cn("rounded-lg border p-3", o.passed ? "border-success/40" : "border-destructive/50")}
          >
            <div className="mb-2 flex items-center gap-2 text-xs">
              <span className="font-medium">{o.model}</span>
              <span className="text-muted-foreground">{RESULTS_COPY.run(o.run_number)}</span>
              <span className={cn("ml-auto font-medium", o.passed ? "text-success" : "text-destructive")}>
                {o.passed ? RESULTS_COPY.pass : RESULTS_COPY.fail}
              </span>
            </div>
            <pre className="font-mono text-xs whitespace-pre-wrap">{o.output ?? o.error}</pre>
            <ul className="text-muted-foreground mt-2 flex flex-col gap-0.5 text-xs">
              {o.scores.map((s) => (
                <li key={s.evaluator_name}>
                  <span className={s.passed ? "text-success" : "text-destructive"}>
                    {s.passed ? "✓" : "✗"}
                  </span>{" "}
                  {s.evaluator_name.replaceAll("_", " ")}: {s.reason}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </article>
  )
}
