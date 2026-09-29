/**
 * The Prompt guide: what a prompt is made of, which techniques are worth using (with the
 * measured evidence and a verdict), rules for testing prompt changes, and how Verano uses
 * all of it (the Improve step reads the same notes). Content is in lib/guide.ts.
 */
import { ArrowUpRight, Ban, CheckCircle2, FlaskConical } from "lucide-react"
import Link from "next/link"

import { Section } from "@/components/common/section"
import { StatusBadge, type Tone } from "@/components/common/status-badge"
import { LAYERS, RULES, TECHNIQUES, type Verdict } from "@/lib/guide"

const VERDICT: Record<Verdict, { label: string; tone: Tone; icon: typeof CheckCircle2 }> = {
  use: { label: "Use it", tone: "success", icon: CheckCircle2 },
  measure: { label: "Measure it", tone: "info", icon: FlaskConical },
  skip: { label: "Skip it", tone: "danger", icon: Ban },
}
const SOURCE = "https://ranjankumar.in/prompt-engineering"

export function GuidePage({ projectId }: { projectId: string }) {
  return (
    <div className="mx-auto flex w-full max-w-[80rem] flex-col gap-6">
      <header className="from-lagoon-soft to-card ring-lagoon/15 flex flex-col gap-3 rounded-2xl bg-gradient-to-br px-6 py-7 ring-1 sm:px-8">
        <p className="text-lagoon-strong text-sm font-medium">Prompt guide</p>
        <h2 className="max-w-[40rem] text-2xl leading-tight font-semibold sm:text-[2rem]">
          Which prompt changes actually help, and how to prove it
        </h2>
        <p className="text-text-secondary max-w-[46rem] text-[0.95rem] leading-relaxed">
          Most prompt advice is a list of tricks with no numbers. Some of it stopped working on newer models.
          Verano exists to measure your prompt, so use this guide to decide what to try, then let a run tell
          you whether it helped. The Improve step reads the same notes when it writes better prompts for you.
        </p>
        <div className="flex flex-wrap gap-3 pt-1 text-sm">
          <Link
            href={`/projects/${projectId}/prompt`}
            className="bg-primary text-primary-foreground rounded-lg px-4 py-2 font-medium"
          >
            Write a prompt
          </Link>
          <Link
            href={`/projects/${projectId}/improve`}
            className="text-lagoon-strong ring-lagoon/30 bg-card rounded-lg px-4 py-2 font-medium ring-1"
          >
            Improve my prompt
          </Link>
        </div>
      </header>

      <Section
        number={1}
        title="A prompt is four different things"
        description="They fail in different ways, so change one at a time."
      >
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {LAYERS.map((layer, index) => (
            <div key={layer.name} className="bg-subtle ring-border flex flex-col gap-2 rounded-xl p-4 ring-1">
              <span className="text-lagoon-strong text-xs font-semibold tabular-nums">Layer {index + 1}</span>
              <h4 className="text-base font-semibold">{layer.name}</h4>
              <p className="text-text-secondary text-sm leading-snug">{layer.text}</p>
              <p className="text-text-muted mt-auto text-xs">{layer.moves}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section
        number={2}
        title="What works, what to measure, what to skip"
        description="Effects were measured on small local models in a public tutorial. Treat them as a starting point."
      >
        <div className="grid gap-3 lg:grid-cols-2">
          {TECHNIQUES.map((technique) => {
            const verdict = VERDICT[technique.verdict]
            return (
              <article
                key={technique.name}
                className="bg-card ring-border flex flex-col gap-2 rounded-xl p-4 ring-1"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="text-base font-semibold">{technique.name}</h4>
                  <StatusBadge tone={verdict.tone} icon={<verdict.icon />}>
                    {verdict.label}
                  </StatusBadge>
                </div>
                <p className="text-sm">{technique.what}</p>
                <dl className="text-text-secondary grid gap-1 text-[0.8125rem] leading-snug">
                  <div>
                    <dt className="text-foreground inline font-medium">When: </dt>
                    <dd className="inline">{technique.when}</dd>
                  </div>
                  <div>
                    <dt className="text-foreground inline font-medium">Effect: </dt>
                    <dd className="inline">{technique.effect}</dd>
                  </div>
                </dl>
                <p className="bg-subtle text-text-secondary rounded-md px-2 py-1 font-mono text-xs break-words">
                  {technique.example}
                </p>
              </article>
            )
          })}
        </div>
      </Section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section number={3} title="Rules for testing a change">
          <ol className="flex flex-col gap-3">
            {RULES.map((rule, index) => (
              <li key={rule} className="flex gap-3 text-sm leading-snug">
                <span className="bg-lagoon-soft text-lagoon-strong flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold tabular-nums">
                  {index + 1}
                </span>
                <span>{rule}</span>
              </li>
            ))}
          </ol>
        </Section>
        <Section number={4} title="How Verano uses this">
          <ul className="text-text-secondary flex list-disc flex-col gap-2 pl-5 text-sm leading-snug">
            <li>
              <span className="text-foreground font-medium">Run and Results</span> give the measurement: pass
              rate, consistency, cost and speed per model.
            </li>
            <li>
              <span className="text-foreground font-medium">Improve</span> is given these notes when it writes
              three candidates, so each one tries a different technique that is known to help, and none is
              built on a trick that is known not to.
            </li>
            <li>
              <span className="text-foreground font-medium">Held-back cases</span> decide the verdict, so a
              candidate that only looks better on the cases it was written from is not accepted.
            </li>
          </ul>
        </Section>
      </div>

      <p className="text-text-secondary flex flex-wrap items-center gap-1 pb-2 text-sm">
        Source and full experiments:
        <a
          href={SOURCE}
          target="_blank"
          rel="noreferrer"
          className="text-lagoon-strong inline-flex items-center gap-0.5 font-medium hover:underline"
        >
          Prompt Engineering Tutorial 2026: Prove Which Prompts Work
          <ArrowUpRight className="size-3.5" />
        </a>
      </p>
    </div>
  )
}
