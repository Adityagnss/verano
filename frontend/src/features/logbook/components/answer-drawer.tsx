/**
 * One answer in full, in a panel beside the table: who answered and how it scored, the
 * golden answer next to the model's answer (a field-by-field check when both are JSON), the
 * scoring checks with their reasons, the other models' answers to the same case, and the
 * exact prompt that was sent.
 */
"use client"

import { Check, X } from "lucide-react"
import { type ReactNode, useEffect } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { StatusBadge } from "@/components/common/status-badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { formatParams } from "@/lib/config"
import { formatCost, formatMs } from "@/lib/format"
import { cn } from "@/lib/utils"

import { compareFields, prettyJson } from "../domain"
import { useAnswer } from "../hooks"

export type Target = { experiment_id: string; run_id: string }

function Block({ title, children, hint }: { title: string; children: ReactNode; hint?: string }) {
  return (
    <section className="flex flex-col gap-2">
      <div>
        <h4 className="text-sm font-semibold">{title}</h4>
        {hint ? <p className="text-text-muted text-xs">{hint}</p> : null}
      </div>
      {children}
    </section>
  )
}

function Code({ text, tone }: { text: string | null | undefined; tone?: "golden" | "answer" }) {
  return (
    <pre
      className={cn(
        "ring-border max-h-80 overflow-auto rounded-lg p-3 font-mono text-xs break-words whitespace-pre-wrap ring-1",
        tone === "golden" ? "bg-gold-soft/50" : "bg-subtle",
      )}
    >
      {text || "—"}
    </pre>
  )
}

function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col">
      <dt className="text-text-muted text-xs">{label}</dt>
      <dd className="text-sm font-medium tabular-nums">{value}</dd>
    </div>
  )
}

export function AnswerDrawer({
  projectId,
  target,
  onClose,
  onOpen,
}: {
  projectId: string
  target: Target | null
  onClose: () => void
  onOpen: (target: Target) => void
}) {
  const detail = useAnswer(projectId, target?.experiment_id ?? null, target?.run_id ?? null)
  useEffect(() => {
    if (!target) return
    const escape = (event: KeyboardEvent) => event.key === "Escape" && onClose()
    document.addEventListener("keydown", escape)
    return () => document.removeEventListener("keydown", escape)
  }, [target, onClose])
  if (!target) return null
  const data = detail.data
  const row = data?.row
  const fields = data ? compareFields(data.golden_answer, data.output) : null
  return (
    <div className="fixed inset-0 z-40" role="dialog" aria-modal="true" aria-label="Answer detail">
      <button
        type="button"
        aria-label="Close"
        className="absolute inset-0 bg-[#14203a]/40"
        onClick={onClose}
      />
      <aside className="bg-card absolute inset-y-0 right-0 flex w-[min(54rem,100vw)] flex-col shadow-2xl">
        <header className="border-border flex items-start justify-between gap-3 border-b px-5 py-4">
          <div className="min-w-0">
            <p className="text-text-secondary text-xs">
              {row ? `${row.experiment} · ${new Date(row.created_at).toLocaleString()}` : "Answer"}
            </p>
            <h3 className="mt-0.5 flex flex-wrap items-center gap-2 text-lg font-semibold">
              {row?.model ?? "Loading…"}
              {row ? <StatusBadge tone="brand">Prompt v{row.prompt_version}</StatusBadge> : null}
              {row ? (
                row.passed === null ? null : row.passed ? (
                  <StatusBadge tone="success">Passed</StatusBadge>
                ) : (
                  <StatusBadge tone="danger">Failed</StatusBadge>
                )
              ) : null}
            </h3>
          </div>
          <Button variant="ghost" size="icon" aria-label="Close" onClick={onClose}>
            <X />
          </Button>
        </header>
        <div className="flex flex-1 flex-col gap-6 overflow-y-auto px-5 py-5">
          <ErrorMessage error={detail.error} />
          {detail.isPending ? <Skeleton className="h-64 w-full" /> : null}
          {data && row ? (
            <>
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <Fact label="Test case" value={`#${row.case_number} · ${row.category}`} />
                <Fact label="Run" value={row.run_number} />
                <Fact
                  label="Quality"
                  value={row.quality === null ? "—" : `${Math.round(row.quality * 100)}%`}
                />
                <Fact
                  label="Golden match"
                  value={row.golden_match === null ? "—" : `${Math.round(row.golden_match * 100)}%`}
                />
                <Fact label="Cost" value={row.cost === null ? "unknown price" : formatCost(row.cost)} />
                <Fact label="Time taken" value={row.latency_ms === null ? "—" : formatMs(row.latency_ms)} />
                <Fact
                  label="Tokens in / out"
                  value={`${row.input_tokens ?? "—"} / ${row.output_tokens ?? "—"}`}
                />
                <Fact label="Settings" value={formatParams(data?.params ?? {})} />
              </dl>
              {row.error ? (
                <p className="bg-danger-soft text-danger-strong rounded-lg p-3 text-sm">{row.error}</p>
              ) : null}

              <Block
                title="Golden answer and model answer"
                hint="Your correct answer on the left, what the model wrote on the right."
              >
                <div className="grid gap-3 md:grid-cols-2">
                  <Code tone="golden" text={prettyJson(data.golden_answer)} />
                  <Code tone="answer" text={prettyJson(data.output)} />
                </div>
              </Block>

              {fields ? (
                <Block
                  title="Field-by-field check"
                  hint="Top-level fields of the golden JSON against the model's JSON."
                >
                  <div className="ring-border overflow-x-auto rounded-lg ring-1">
                    <table className="w-full min-w-[32rem] text-left text-sm">
                      <thead className="bg-subtle text-text-secondary text-xs">
                        <tr>
                          <th className="px-3 py-2">Field</th>
                          <th className="px-3 py-2">Golden</th>
                          <th className="px-3 py-2">Model</th>
                          <th className="px-3 py-2">Match</th>
                        </tr>
                      </thead>
                      <tbody>
                        {fields.map((f) => (
                          <tr key={f.field} className="border-border border-t align-top">
                            <td className="px-3 py-2 font-mono text-xs">{f.field}</td>
                            <td className="px-3 py-2 font-mono text-xs break-words">{f.golden}</td>
                            <td className="px-3 py-2 font-mono text-xs break-words">{f.answer}</td>
                            <td className="px-3 py-2">
                              {f.match === null ? (
                                <span className="text-text-muted text-xs">extra field</span>
                              ) : f.match ? (
                                <StatusBadge tone="success" icon={<Check />}>
                                  Same
                                </StatusBadge>
                              ) : (
                                <StatusBadge tone="danger" icon={<X />}>
                                  Different
                                </StatusBadge>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Block>
              ) : null}

              <Block title="Scoring checks" hint="Each check that judged this answer, its score and why.">
                {data.scores.length === 0 ? (
                  <p className="text-text-secondary text-sm">No check applied to this answer.</p>
                ) : (
                  <ul className="flex flex-col gap-2">
                    {data.scores.map((s) => (
                      <li
                        key={s.evaluator}
                        className="bg-subtle ring-border flex flex-col gap-1 rounded-lg p-3 ring-1"
                      >
                        <div className="flex flex-wrap items-center gap-2 text-sm">
                          <span className="font-medium capitalize">{s.evaluator.replaceAll("_", " ")}</span>
                          <StatusBadge tone={s.passed ? "success" : "danger"}>
                            {s.passed ? "Passed" : "Failed"}
                          </StatusBadge>
                          <span className="text-text-secondary tabular-nums">
                            score {Math.round(s.value * 100)}%
                          </span>
                          {s.required ? <StatusBadge tone="brand">Must pass</StatusBadge> : null}
                        </div>
                        <p className="text-text-secondary text-xs">{s.reason}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </Block>

              {data.siblings.length > 0 ? (
                <Block
                  title="Other answers to this test case"
                  hint="Same experiment, same case. Click one to open it."
                >
                  <ul className="flex flex-col gap-2">
                    {data.siblings.map((s) => (
                      <li key={s.run_id}>
                        <button
                          type="button"
                          onClick={() => onOpen({ experiment_id: row.experiment_id, run_id: s.run_id })}
                          className="ring-border hover:bg-lagoon-soft/40 flex w-full flex-col gap-1 rounded-lg p-3 text-left ring-1"
                        >
                          <span className="flex flex-wrap items-center gap-2 text-sm">
                            <span className="font-medium">{s.model}</span>
                            <span className="text-text-muted text-xs">run {s.run_number}</span>
                            {s.passed === null ? null : (
                              <StatusBadge tone={s.passed ? "success" : "danger"}>
                                {s.passed ? "Passed" : "Failed"}
                              </StatusBadge>
                            )}
                            <span className="text-text-secondary text-xs tabular-nums">
                              {s.cost === null ? "unknown price" : formatCost(s.cost)} ·{" "}
                              {s.latency_ms === null ? "—" : formatMs(s.latency_ms)}
                            </span>
                          </span>
                          <span className="text-text-secondary line-clamp-2 font-mono text-xs">
                            {s.output ?? s.error ?? "—"}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </Block>
              ) : null}

              <Block
                title="Exact prompt sent"
                hint="What the model actually received, after your variables and input file were filled in."
              >
                <details>
                  <summary className="text-lagoon-strong cursor-pointer text-sm font-medium">
                    Show the prompt
                  </summary>
                  <div className="mt-2 flex flex-col gap-2">
                    {data.rendered_system_prompt ? (
                      <>
                        <p className="text-text-secondary text-xs font-medium">System</p>
                        <Code text={data.rendered_system_prompt} />
                      </>
                    ) : null}
                    {data.rendered_user_prompt ? (
                      <>
                        <p className="text-text-secondary text-xs font-medium">User message</p>
                        <Code text={data.rendered_user_prompt} />
                      </>
                    ) : null}
                  </div>
                </details>
              </Block>
            </>
          ) : null}
        </div>
      </aside>
    </div>
  )
}
