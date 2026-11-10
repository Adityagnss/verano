/**
 * Step 1, Keys: add provider keys, see what each key reaches, and choose the models to
 * test. The choice is kept on screen until the one primary action saves it, so browsing
 * and un-ticking are free; saving sends only what changed.
 */
"use client"

import { useRouter } from "next/navigation"
import { useCallback, useMemo, useState } from "react"
import { toast } from "sonner"

import { EmptyState } from "@/components/common/empty-state"
import { ErrorMessage } from "@/components/common/error-message"
import { PageActions } from "@/components/common/page-actions"
import { Section } from "@/components/common/section"
import { StatusBadge } from "@/components/common/status-badge"
import { PageIntro } from "@/components/common/page-intro"
import { Button } from "@/components/ui/button"
import type { ProviderOut } from "@/lib/api/types"
import { ALL_PROJECT_PAGES, projectHref } from "@/lib/nav"

import { KEYS_COPY } from "../copy"
import { useCredentials, useModels, useProviders, useSaveSelection } from "../hooks"
import { AddKeyDialog } from "./add-key-dialog"
import { CredentialList } from "./credential-list"
import { ModelTable } from "./model-table"
import { ProviderGrid } from "./provider-grid"
import { SharedKeys } from "./shared-keys"
import { SuggestedModels } from "./suggested-models"

const PAGE = ALL_PROJECT_PAGES.find((p) => p.key === "keys")!
const NEXT = ALL_PROJECT_PAGES.find((p) => p.key === "prompt")!

export function KeysStep({ projectId }: { projectId: string }) {
  const router = useRouter()
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

  /** Tick exactly these models, unticking the rest. */
  const useOnly = useCallback(
    (ids: string[]) => {
      const wanted = new Set(ids)
      const next = new Map<string, boolean>()
      ;(models.data ?? []).forEach((m) => {
        if (wanted.has(m.id) !== saved.has(m.id)) next.set(m.id, wanted.has(m.id))
      })
      setChanges(next)
    },
    [models.data, saved],
  )

  async function saveSelection() {
    await save.mutateAsync({
      selected: [...selected].filter((id) => !saved.has(id)),
      unselected: [...saved].filter((id) => !selected.has(id)),
    })
    setChanges(new Map())
    toast.success(KEYS_COPY.saved)
    router.push(projectHref(projectId, NEXT))
  }

  const unknownPrice = (models.data ?? []).some((m) => selected.has(m.id) && !m.price_known)
  return (
    <div className="mx-auto flex w-full max-w-[96rem] flex-col gap-6">
      <PageIntro
        storageKey="keys"
        title={PAGE.label}
        what={KEYS_COPY.intro.what}
        whenToUse={KEYS_COPY.intro.whenToUse}
        youGet={KEYS_COPY.intro.youGet}
        learnMore="keys"
        hasContent={(credentials.data?.length ?? 0) > 0}
        primaryAction={
          (credentials.data?.length ?? 0) === 0 ? (
            <Button
              size="lg"
              onClick={() => document.getElementById("providers")?.scrollIntoView({ behavior: "smooth" })}
            >
              {KEYS_COPY.intro.connectFirst}
            </Button>
          ) : null
        }
      />
      <ErrorMessage error={providers.error ?? credentials.error ?? models.error} />
      <div id="providers" className="scroll-mt-20" />
      <Section number={1} title={KEYS_COPY.providersHeading} description={KEYS_COPY.providersDescription}>
        <ProviderGrid
          providers={providers.data ?? []}
          credentials={credentials.data ?? []}
          onAdd={setAdding}
        />
        <SharedKeys projectId={projectId} providerNames={providerNames} />
      </Section>
      <Section
        number={2}
        title={KEYS_COPY.keysHeading}
        description={KEYS_COPY.keysDescription}
        badge={
          credentials.data?.length ? (
            <StatusBadge tone="success">{credentials.data.length}</StatusBadge>
          ) : null
        }
      >
        <CredentialList
          projectId={projectId}
          credentials={credentials.data ?? []}
          providerNames={providerNames}
        />
      </Section>
      <Section
        number={3}
        title={KEYS_COPY.modelsHeading}
        description={KEYS_COPY.modelsDescription}
        badge={
          selected.size ? <StatusBadge tone="brand">{KEYS_COPY.selected(selected.size)}</StatusBadge> : null
        }
      >
        {models.data && models.data.length > 0 ? (
          <SuggestedModels models={models.data} selected={selected} onUse={useOnly} />
        ) : null}
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
            {unknownPrice ? (
              <span className="text-warning-strong">{KEYS_COPY.unknownPriceWarning}</span>
            ) : null}
            <ErrorMessage error={save.error} />
          </div>
        }
      >
        <Button
          size="lg"
          onClick={() => void saveSelection().catch(() => undefined)}
          disabled={selected.size === 0 || save.isPending}
        >
          {KEYS_COPY.continueWith(selected.size)}
        </Button>
      </PageActions>
      <AddKeyDialog projectId={projectId} provider={adding} onClose={() => setAdding(null)} />
    </div>
  )
}
