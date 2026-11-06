/**
 * One test case as a compact row (its input, source and a pass/fail pill per model and run)
 * that opens to show every model's output side by side with each evaluator's reason.
 * Uses <details>, so it works with the keyboard and screen readers without extra code.
 */
import { ChevronRight, CircleAlert, CircleCheck, CircleX } from "lucide-react"

import { StatusBadge } from "@/components/common/status-badge"
import type { CaseResultOut } from "@/lib/api/types"
import { cn } from "@/lib/utils"

import { LABEL_COPY, RESULTS_COPY } from "../copy"
import { EvidencePanel } from "./evidence-panel"
import { JudgeCalls } from "./judge-calls"
import { LabelBar } from "./label-bar"

function inputText(item: CaseResultOut): string {
  const values = Object.values(item.inputs)
  return values.length === 1 ? String(values[0]) : JSON.stringify(item.inputs)
}

export function CaseView({
  item,
  projectId,
  experimentId,
}: {
  item: CaseResultOut
  projectId: string
  experimentId: string
}) {
  const failed = item.outputs.filter((o) => o.judged && !o.passed).length
  const notJudged = item.outputs.filter((o) => !o.judged).length
  return (
    <details className="group bg-card border-border open:ring-border-strong rounded-lg border open:ring-1">
      <summary className="hover:bg-subtle/60 flex cursor-pointer list-none items-center gap-3 rounded-lg px-4 py-3 [&::-webkit-details-marker]:hidden">
        <ChevronRight className="text-text-muted size-4 shrink-0 transition-transform group-open:rotate-90" />
        <span className="min-w-0 flex-1 truncate font-mono text-xs">{inputText(item)}</span>
        <span className="flex shrink-0 flex-wrap justify-end gap-1">
          {item.outputs.map((o) => (
            <StatusBadge
              key={o.test_case_run_id}
              tone={!o.judged ? "warning" : o.passed ? "success" : "danger"}
              icon={!o.judged ? <CircleAlert /> : o.passed ? <CircleCheck /> : <CircleX />}
            >
              {o.model}
              {o.run_number > 1 ? ` #${o.run_number}` : ""}
            </StatusBadge>
          ))}
        </span>
      </summary>
      <div className="border-border flex flex-col gap-3 border-t p-4">
        <header className="flex flex-wrap items-center gap-2">
          <StatusBadge tone="neutral">{item.category.replaceAll("_", " ")}</StatusBadge>
          <StatusBadge
            tone={item.source === "golden" ? "gold" : item.source === "generated" ? "violet" : "info"}
          >
            {item.source.replace("_", " ")}
          </StatusBadge>
          {item.split ? (
            <StatusBadge tone="neutral">{item.split === "holdout" ? "held back" : "improve"}</StatusBadge>
          ) : null}
          {notJudged ? (
            <StatusBadge tone="warning" icon={<CircleAlert />} className="ml-auto">
              {notJudged} {RESULTS_COPY.notJudged.toLowerCase()}
            </StatusBadge>
          ) : null}
          {failed ? (
            <StatusBadge tone="danger" icon={<CircleX />} className={notJudged ? "" : "ml-auto"}>
              {failed} failed
            </StatusBadge>
          ) : notJudged ? null : (
            <StatusBadge tone="success" icon={<CircleCheck />} className="ml-auto">
              all passed
            </StatusBadge>
          )}
        </header>
        <pre className="bg-subtle ring-border rounded-lg p-3 font-mono text-xs whitespace-pre-wrap ring-1">
          {Object.entries(item.inputs)
            .map(([key, value]) => `${key}: ${String(value)}`)
            .join("\n")}
        </pre>
        {item.expected_output ? (
          <p className="text-sm">
            <span className="text-text-muted">{RESULTS_COPY.expected}: </span>
            <span className="font-mono">{item.expected_output}</span>
          </p>
        ) : null}
        {item.agreement.length ? (
          <ul className="text-text-secondary flex flex-col gap-0.5 text-xs">
            {item.agreement.map((a) => (
              <li key={a.model_profile_id}>
                {RESULTS_COPY.agreement(
                  item.outputs.find((o) => o.model_profile_id === a.model_profile_id)?.model ?? "",
                  a.same,
                  a.runs,
                )}
              </li>
            ))}
          </ul>
        ) : null}
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {item.outputs.map((o) => (
            <div
              key={o.test_case_run_id}
              className={cn(
                "rounded-lg border p-3",
                !o.judged
                  ? "border-warning/40 bg-warning-soft/40"
                  : o.passed
                    ? "border-success/40 bg-success-soft/40"
                    : "border-danger/40 bg-danger-soft/40",
              )}
            >
              <div className="mb-2 flex items-center gap-2 text-xs">
                <span className="font-medium">{o.model}</span>
                <span className="text-muted-foreground">{RESULTS_COPY.run(o.run_number)}</span>
                <StatusBadge
                  tone={!o.judged ? "warning" : o.passed ? "success" : "danger"}
                  icon={!o.judged ? <CircleAlert /> : o.passed ? <CircleCheck /> : <CircleX />}
                  className="ml-auto"
                >
                  {!o.judged ? RESULTS_COPY.notJudged : o.passed ? RESULTS_COPY.pass : RESULTS_COPY.fail}
                </StatusBadge>
              </div>
              <pre className="font-mono text-xs whitespace-pre-wrap">{o.output ?? o.error}</pre>
              {o.truncated ? (
                <p className="text-warning-strong mt-1 text-xs">{LABEL_COPY.truncated}</p>
              ) : null}
              {o.retrieved_chunks?.length ? (
                <details className="mt-2 text-xs">
                  <summary className="text-text-muted cursor-pointer">
                    {LABEL_COPY.chunks} ({o.retrieved_chunks.length})
                  </summary>
                  <ul className="mt-1 flex flex-col gap-1">
                    {o.retrieved_chunks.map((chunk, index) => (
                      <li key={index} className="bg-subtle ring-border rounded p-2 ring-1">
                        {String(chunk)}
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
              {o.tool_calls?.length ? (
                <details className="mt-2 text-xs">
                  <summary className="text-text-muted cursor-pointer">
                    {LABEL_COPY.toolCalls} ({o.tool_calls.length})
                  </summary>
                  <pre className="bg-subtle ring-border mt-1 rounded p-2 font-mono ring-1">
                    {JSON.stringify(o.tool_calls, null, 2)}
                  </pre>
                </details>
              ) : null}
              <ul className="text-text-secondary mt-2 flex flex-col gap-0.5 text-xs">
                {o.scores.map((s) =>
                  s.status === "unscored" ? (
                    <li key={s.evaluator_name} className="text-warning-strong">
                      <span>!</span> {s.evaluator_name.replaceAll("_", " ")}: {RESULTS_COPY.notJudgedWhy}{" "}
                      {s.reason}
                    </li>
                  ) : (
                    <li key={s.evaluator_name}>
                      <span className={s.passed ? "text-success" : "text-destructive"}>
                        {s.passed ? "✓" : "✗"}
                      </span>{" "}
                      {s.evaluator_name.replaceAll("_", " ")}: {s.reason}
                    </li>
                  ),
                )}
              </ul>
              {o.hidden ? null : (
                <LabelBar
                  projectId={projectId}
                  experimentId={experimentId}
                  answerId={o.test_case_run_id}
                  labels={o.labels}
                />
              )}
              {o.scores.length ? (
                <>
                  <EvidencePanel
                    projectId={projectId}
                    experimentId={experimentId}
                    answerId={o.test_case_run_id}
                  />
                  <JudgeCalls
                    projectId={projectId}
                    experimentId={experimentId}
                    answerId={o.test_case_run_id}
                  />
                </>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </details>
  )
}
