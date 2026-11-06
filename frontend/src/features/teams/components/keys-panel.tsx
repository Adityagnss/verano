/** Workspace keys: a provider key stored once, used by many projects, rotated in one place. */
"use client"

import { type FormEvent, useState } from "react"
import { toast } from "sonner"

import { ErrorMessage } from "@/components/common/error-message"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { NativeSelect } from "@/components/ui/select"
import { useProviders } from "@/features/keys/hooks"
import { useProjects } from "@/features/projects/hooks"
import type { MembershipRole, OrgKeyOut } from "@/lib/api/types"

import { atLeast, dateTime } from "../domain"
import {
  useCreateOrgKey,
  useDeleteOrgKey,
  useOrgKeys,
  useRotateOrgKey,
  useStopUsingKey,
  useUseKeyInProject,
} from "../hooks"

type Props = { organizationId: string; role: MembershipRole }

function KeyCard({ k, organizationId, manage }: { k: OrgKeyOut; organizationId: string; manage: boolean }) {
  const rotate = useRotateOrgKey(organizationId)
  const remove = useDeleteOrgKey(organizationId)
  const use = useUseKeyInProject(organizationId)
  const stop = useStopUsingKey(organizationId)
  const projects = useProjects()
  const [newKey, setNewKey] = useState("")
  const [rotating, setRotating] = useState(false)
  const [project, setProject] = useState("")
  const free = (projects.data?.items ?? []).filter(
    (p) => p.organization_id === organizationId && !k.used_in.some((u) => u.project_id === p.id),
  )

  async function doRotate(event: FormEvent) {
    event.preventDefault()
    await rotate.mutateAsync({ keyId: k.id, apiKey: newKey })
    setNewKey("")
    setRotating(false)
    toast.success("Key rotated. Every project using it now uses the new key.")
  }

  return (
    <li className="border-border flex flex-col gap-3 rounded-xl border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium">
          {k.label || k.provider} <span className="text-text-muted">ending {k.key_last4 ?? "----"}</span>
        </span>
        <span className="text-text-secondary text-xs">
          {k.rotated_at ? `Rotated ${dateTime(k.rotated_at)}` : `Added ${dateTime(k.created_at)}`}
        </span>
      </div>
      <p className="text-text-secondary text-sm">
        Used in:{" "}
        {k.used_in.length
          ? k.used_in.map((u) => (
              <Badge key={u.project_id} variant="secondary" className="mr-1">
                {u.project_name}
                {manage ? (
                  <button
                    className="ml-1"
                    aria-label={`Stop using in ${u.project_name}`}
                    onClick={() => stop.mutate({ keyId: k.id, projectId: u.project_id })}
                  >
                    ×
                  </button>
                ) : null}
              </Badge>
            ))
          : "no project yet"}
      </p>
      <ErrorMessage error={rotate.error ?? remove.error ?? use.error ?? stop.error} />
      {manage ? (
        <div className="flex flex-wrap items-center gap-2">
          <NativeSelect
            aria-label="Use in a project"
            value={project}
            onChange={(e) => setProject(e.target.value)}
            className="h-8 w-48"
          >
            <option value="">Use in a project...</option>
            {free.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </NativeSelect>
          <Button
            size="sm"
            variant="outline"
            disabled={!project || use.isPending}
            onClick={() =>
              void use.mutateAsync({ keyId: k.id, projectId: project }).then(
                () => setProject(""),
                () => undefined,
              )
            }
          >
            Add to project
          </Button>
          <Button size="sm" variant="outline" onClick={() => setRotating(!rotating)}>
            Rotate
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              if (window.confirm("Remove this key from the workspace?")) remove.mutate(k.id)
            }}
          >
            Remove
          </Button>
        </div>
      ) : null}
      {rotating ? (
        <form onSubmit={(e) => void doRotate(e).catch(() => undefined)} className="flex flex-col gap-2">
          <p className="text-text-secondary text-xs">
            The new key is checked with the provider first. Once saved, the old key is used nowhere.
          </p>
          <div className="flex gap-2">
            <Input
              type="password"
              required
              autoComplete="off"
              aria-label="New API key"
              placeholder="Paste the new key"
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
            />
            <Button type="submit" disabled={rotate.isPending}>
              Replace everywhere
            </Button>
          </div>
        </form>
      ) : null}
    </li>
  )
}

export function KeysPanel({ organizationId, role }: Props) {
  const manage = atLeast(role, "admin")
  const keys = useOrgKeys(organizationId, true)
  const providers = useProviders()
  const create = useCreateOrgKey(organizationId)
  const [provider, setProvider] = useState("")
  const [apiKey, setApiKey] = useState("")
  const [label, setLabel] = useState("")
  const keyed = (providers.data ?? []).filter((p) => p.requires_key)

  async function add(event: FormEvent) {
    event.preventDefault()
    await create.mutateAsync({ provider, api_key: apiKey, label: label || null })
    setApiKey("")
    setLabel("")
    toast.success("Key stored for the workspace.")
  }

  return (
    <div className="flex flex-col gap-5">
      <p className="text-text-secondary text-sm">
        Store a provider key once and use it in as many projects as you like. Rotating it here changes it for
        all of them.
      </p>
      <ErrorMessage error={keys.error} />
      <ul className="flex flex-col gap-3">
        {(keys.data ?? []).map((k) => (
          <KeyCard key={k.id} k={k} organizationId={organizationId} manage={manage} />
        ))}
        {keys.data?.length === 0 ? <li className="text-text-muted text-sm">No workspace keys yet.</li> : null}
      </ul>
      {manage ? (
        <form onSubmit={(e) => void add(e).catch(() => undefined)} className="flex flex-col gap-2">
          <h3 className="text-base font-semibold">Add a key</h3>
          <div className="flex flex-wrap gap-2">
            <NativeSelect
              aria-label="Provider"
              required
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              className="h-9 w-48"
            >
              <option value="">Provider...</option>
              {keyed.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.display_name}
                </option>
              ))}
            </NativeSelect>
            <Input
              type="password"
              required
              autoComplete="off"
              aria-label="API key"
              placeholder="API key"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              className="w-72"
            />
            <Input
              aria-label="Name (optional)"
              placeholder="Name (optional)"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="w-48"
            />
            <Button type="submit" disabled={create.isPending}>
              Store key
            </Button>
          </div>
          <ErrorMessage error={create.error} />
        </form>
      ) : null}
    </div>
  )
}
