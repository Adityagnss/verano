/**
 * Step 1, Keys: add provider keys, see what each key reaches, and choose the models to
 * test. The choice is kept on screen until the one primary action saves it, so browsing
 * and un-ticking are free; saving sends only what changed.
 */
"use client"

import { useCallback, useMemo, useState } from "react"
import { toast } from "sonner"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { PageActions } from "@/components/common/page-actions"
import { Button } from "@/components/ui/button"
import type { ProviderOut } from "@/lib/api/types"

import { KEYS_COPY } from "../copy"
import { useCredentials, useModels, useProviders, useSaveSelection } from "../hooks"
import { AddKeyDialog } from "./add-key-dialog"
import { CredentialList } from "./credential-list"
import { ModelTable } from "./model-table"
import { ProviderGrid } from "./provider-grid"

function Section({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: React.ReactNode
}) {
  return (
    <section className="flex flex-col gap-3">
      <div>
        <h3 className="text-sm font-medium">{title}</h3>
        {description ? <p className="text-muted-foreground text-sm">{description}</p> : null}
      </div>
      {children}
    </section>
  )
}

export function KeysStep({ projectId }: { projectId: string }) {
  const providers = useProviders()
  const credentials = useCredentials(projectId)
  const models = useModels(projectId)
  const save = useSaveSelection(projectId)
  const [adding, setAdding] = useState<ProviderOut | null>(null)
  const [changes, setChanges] = useState<Map<string, boolean>>(new Map())

  const providerNames = useMemo(
    () =>
      Object.fromEntries((providers.data ?? []).map((provider) => [provider.name, provider.display_name])),
    [providers.data],
  )
  const saved = useMemo(
    () => new Set((models.data ?? []).filter((m) => m.is_selected).map((m) => m.id)),
    [models.data],
  )
  const selected = useMemo(() => {
    const current = new Set(saved)
    changes.forEach((checked, id) => (checked ? current.add(id) : current.delete(id)))
    return current
  }, [saved, changes])
  const toggle = useCallback((id: string, checked: boolean) => {
    setChanges((previous) => new Map(previous).set(id, checked))
  }, [])

  async function saveSelection() {
    await save.mutateAsync({
      selected: [...selected].filter((id) => !saved.has(id)),
      unselected: [...saved].filter((id) => !selected.has(id)),
    })
    setChanges(new Map())
    toast.success(KEYS_COPY.saved)
  }

  const unknownPrice = (models.data ?? []).some((m) => selected.has(m.id) && !m.price_known)
  return (
    <div className="flex max-w-5xl flex-col gap-8">
      <div>
        <h2 className="text-xl font-semibold">{KEYS_COPY.title}</h2>
        <p className="text-muted-foreground mt-1 max-w-3xl text-sm">{KEYS_COPY.subtitle}</p>
      </div>
      <ErrorMessage error={providers.error ?? credentials.error ?? models.error} />
      <Section title={KEYS_COPY.providersHeading}>
        <ProviderGrid providers={providers.data ?? []} onAdd={setAdding} />
      </Section>
      <Section title={KEYS_COPY.keysHeading}>
        <CredentialList
          projectId={projectId}
          credentials={credentials.data ?? []}
          providerNames={providerNames}
        />
      </Section>
      <Section title={KEYS_COPY.modelsHeading} description={KEYS_COPY.modelsDescription}>
        {models.data && models.data.length > 0 ? (
          <ModelTable
            models={models.data}
            providerNames={providerNames}
            selected={selected}
            onToggle={toggle}
          />
        ) : (
          <EmptyState title={KEYS_COPY.noModelsTitle} description={KEYS_COPY.noModelsDescription} />
        )}
      </Section>
      <PageActions
        summary={
          <div className="flex flex-col gap-1">
            <span>{KEYS_COPY.selected(selected.size)}</span>
            {unknownPrice ? <span className="text-warning">{KEYS_COPY.unknownPriceWarning}</span> : null}
            <ErrorMessage error={save.error} />
          </div>
        }
      >
        <Button
          size="lg"
          onClick={() => void saveSelection().catch(() => undefined)}
          disabled={selected.size === 0 || save.isPending}
        >
          {KEYS_COPY.useSelected(selected.size)}
        </Button>
      </PageActions>
      <AddKeyDialog projectId={projectId} provider={adding} onClose={() => setAdding(null)} />
    </div>
  )
}
