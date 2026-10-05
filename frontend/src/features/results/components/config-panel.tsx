/**
 * The run configuration of one experiment, grouped as what you set, what Verano locks and
 * records, and what the provider controls, with a "same configuration" badge when other
 * experiments in the project were set up identically.
 */
"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ErrorMessage } from "@/components/common/error-message"
import { Section } from "@/components/common/section"
import type { ExperimentOut } from "@/lib/api/types"
import { RESULTS_COPY } from "../copy"
import { useReplication, useRerun } from "../hooks"
import { comparisonText } from "./comparison-detail"
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
  const router = useRouter()
  const rerun = useRerun(projectId)
  const c = experiment.configuration
  const same = sameConfiguration(all, experiment.id, (e) => e.configuration.hash)
  const earlier = same
    .filter(
      (e) => e.created_at < experiment.created_at && ["completed", "cancelled", "failed"].includes(e.status),
    )
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
  const replication = useReplication(projectId, experiment.id, earlier?.id ?? null)
  return (
    <Section
      title="Run configuration"
      description="Everything this experiment was set up with, in three groups."
      action={
        <Button
          variant="outline"
          size="sm"
          title={RESULTS_COPY.rerunHint}
          disabled={rerun.isPending}
          onClick={() =>
            rerun.mutate(experiment.id, { onSuccess: () => router.push(`/projects/${projectId}/run`) })
          }
        >
          {rerun.isPending ? RESULTS_COPY.rerunning : RESULTS_COPY.rerun}
        </Button>
      }
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
      <ErrorMessage error={rerun.error} />
      {replication.data ? (
        <div className="bg-subtle ring-border rounded-lg p-3 text-sm ring-1">
          <p className="font-medium">
            {RESULTS_COPY.replication(
              replication.data.same,
              replication.data.compared,
              replication.data.against_name,
            )}
          </p>
          {replication.data.skipped ? (
            <p className="text-text-muted text-xs">
              {RESULTS_COPY.replicationSkipped(replication.data.skipped)}
            </p>
          ) : null}
          {replication.data.models
            .filter((m) => m.model_changed)
            .map((m) => (
              <p key={m.model_profile_id} className="text-warning-strong text-xs">
                {RESULTS_COPY.versionChangedBetween(m.model, m.earlier_versions, m.versions)}
              </p>
            ))}
          {replication.data.models
            .filter((m) => m.quality)
            .map((m) => (
              <p
                key={`q-${m.model_profile_id}`}
                className="text-text-secondary text-xs"
                title={comparisonText(m.quality!)}
              >
                {m.model}:{" "}
                {RESULTS_COPY.rerunQuality(RESULTS_COPY.labels[m.quality!.label] ?? m.quality!.label)}
              </p>
            ))}
          <p className="text-text-muted text-xs">{RESULTS_COPY.replicationNote}</p>
        </div>
      ) : null}
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
          <Item label="Model version the provider reported">
            <ul className="flex flex-col gap-1.5">
              {experiment.model_versions.map((v) => (
                <li key={v.model_profile_id}>
                  <span className="font-medium">{v.display_name}</span>
                  {v.returned.length === 0 ? (
                    <span className="text-text-muted block text-xs">No answers yet.</span>
                  ) : (
                    v.returned.map((r) => (
                      <span key={r.id ?? "none"} className="text-text-muted block text-xs">
                        {r.id ?? "not reported"} · {r.calls} call{r.calls === 1 ? "" : "s"}
                      </span>
                    ))
                  )}
                  {v.changed ? (
                    <span className="text-warning-strong block text-xs">
                      {RESULTS_COPY.versionChangedWithin}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          </Item>
          <Item label="Not guaranteed">{CONFIG_LAYERS.wording}</Item>
        </Layer>
      </div>
    </Section>
  )
}
