/**
 * The run configuration of one experiment, grouped as what you set, what Verano locks and
 * records, and what the provider controls, with a "same configuration" badge when other
 * experiments in the project were set up identically.
 */
"use client"

import Link from "next/link"

import { Badge } from "@/components/ui/badge"
import { Section } from "@/components/common/section"
import type { ExperimentOut } from "@/lib/api/types"
import { CONFIG_LAYERS, formatParams, sameConfiguration, shortHash } from "@/lib/config"

function Layer({ title, text, children }: { title: string; text: string; children: React.ReactNode }) {
  return (
    <div className="bg-subtle ring-border flex flex-col gap-3 rounded-lg p-4 ring-1">
      <div>
        <h3 className="text-sm font-semibold">{title}</h3>
        <p className="text-text-muted mt-0.5 text-xs">{text}</p>
      </div>
      <dl className="flex flex-col gap-2 text-sm">{children}</dl>
    </div>
  )
}

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-text-muted text-xs">{label}</dt>
      <dd className="break-words">{children}</dd>
    </div>
  )
}

export function ConfigPanel({
  projectId,
  experiment,
  all,
}: {
  projectId: string
  experiment: ExperimentOut
  all: ExperimentOut[]
}) {
  const c = experiment.configuration
  const same = sameConfiguration(all, experiment.id, (e) => e.configuration.hash)
  return (
    <Section
      title="Run configuration"
      description="Everything this experiment was set up with, in three groups."
      badge={
        <Badge variant={same.length ? "default" : "outline"} title={c.hash}>
          {same.length ? "Same configuration" : "Configuration"} · {shortHash(c.hash)}
        </Badge>
      }
    >
      {same.length ? (
        <p className="text-sm">
          Set up the same way as{" "}
          {same.map((e, index) => (
            <span key={e.id}>
              {index > 0 ? ", " : ""}
              <Link href={`/projects/${projectId}/results?experiment=${e.id}`} className="text-accent">
                {e.name}
              </Link>
            </span>
          ))}
          . {CONFIG_LAYERS.wording}
        </p>
      ) : (
        <p className="text-text-muted text-sm">No other experiment in this project has this configuration.</p>
      )}
      <div className="grid gap-4 lg:grid-cols-3">
        <Layer {...CONFIG_LAYERS.youSet}>
          <Item label="Prompt">{c.prompt_version ? `Version ${c.prompt_version}` : "—"}</Item>
          <Item label="Test cases">
            {c.split_scope === "all" ? "All approved cases" : `${c.split_scope} part only`}
          </Item>
          <Item label="Judge model">{c.judge_model ?? "None (no judged checks)"}</Item>
          <Item label="Models">
            <ul className="flex flex-col gap-1.5">
              {c.models.map((m) => (
                <li key={m.model_profile_id}>
                  <span className="font-medium">{m.display_name}</span> · {m.runs} run
                  {m.runs === 1 ? "" : "s"}
                  <br />
                  <span className="text-text-muted text-xs">{formatParams(m.params)}</span>
                  {m.ignored_params.length ? (
                    <span className="text-warning-strong block text-xs">
                      Not used by this model: {m.ignored_params.join(", ").replaceAll("_", " ")}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          </Item>
        </Layer>
        <Layer {...CONFIG_LAYERS.locked}>
          <Item label="Configuration fingerprint">
            <code className="text-xs break-all">{c.hash}</code>
          </Item>
          <Item label="Experiment id">
            <code className="text-xs">{experiment.id}</code>
          </Item>
          <Item label="Libraries">
            {Object.entries(c.libraries)
              .map(([name, version]) => `${name} ${version ?? "unknown"}`)
              .join(" · ") || "—"}
          </Item>
        </Layer>
        <Layer {...CONFIG_LAYERS.provider}>
          <Item label="Not guaranteed">{CONFIG_LAYERS.wording}</Item>
        </Layer>
      </div>
    </Section>
  )
}
