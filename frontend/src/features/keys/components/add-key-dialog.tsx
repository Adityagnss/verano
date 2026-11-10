/**
 * Dialog that adds one credential. For keyed providers it asks for the key; key-less local
 * providers (Ollama) ask only for the address. Optional rate-limit overrides sit behind
 * "Advanced" because most users never need them. A rejected key shows the provider's
 * reason and what to do, and nothing is saved.
 */
"use client"

import { ChevronRight } from "lucide-react"
import { type FormEvent, useState } from "react"
import { toast } from "sonner"

import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { CredentialCreate, ProviderOut } from "@/lib/api/types"

import { KEYS_COPY } from "../copy"
import { useAddCredential } from "../hooks"

function optionalNumber(value: FormDataEntryValue | null): number | null {
  const text = String(value ?? "").trim()
  return text ? Number(text) : null
}

function optionalText(value: FormDataEntryValue | null): string | null {
  const text = String(value ?? "").trim()
  return text || null
}

function toBody(provider: ProviderOut, form: FormData): CredentialCreate {
  return {
    provider: provider.name,
    api_key: provider.requires_key ? optionalText(form.get("api_key")) : null,
    base_url: optionalText(form.get("base_url")),
    label: optionalText(form.get("label")),
    rpm_limit: optionalNumber(form.get("rpm_limit")),
    tpm_limit: optionalNumber(form.get("tpm_limit")),
  }
}

type Props = { projectId: string; provider: ProviderOut | null; onClose: () => void }

export function AddKeyDialog({ projectId, provider, onClose }: Props) {
  const add = useAddCredential(projectId)
  const [advanced, setAdvanced] = useState(false)

  function close() {
    add.reset()
    setAdvanced(false)
    onClose()
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!provider) return
    const credential = await add.mutateAsync(toBody(provider, new FormData(event.currentTarget)))
    toast.success(KEYS_COPY.foundModels(credential.model_count))
    close()
  }

  const title = provider?.requires_key ? KEYS_COPY.dialogTitle : KEYS_COPY.connectTitle
  return (
    <Sheet open={provider !== null} onOpenChange={(open) => (open ? undefined : close())}>
      <SheetContent className="overflow-y-auto p-4 data-[side=right]:w-full">
        {provider ? (
          <form
            onSubmit={(event) => void submit(event).catch(() => undefined)}
            className="flex flex-col gap-4"
          >
            <SheetHeader>
              <SheetTitle>{title(provider.display_name)}</SheetTitle>
              <SheetDescription>{KEYS_COPY.dialogDescription}</SheetDescription>
            </SheetHeader>
            {provider.requires_key ? (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="api_key">{KEYS_COPY.apiKey}</Label>
                <Input
                  id="api_key"
                  name="api_key"
                  type="password"
                  autoComplete="off"
                  required
                  className="font-mono"
                />
              </div>
            ) : null}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="base_url">{KEYS_COPY.baseUrl}</Label>
              <Input
                id="base_url"
                name="base_url"
                placeholder={provider.default_base_url ?? ""}
                className="font-mono"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="label">{KEYS_COPY.label}</Label>
              <Input id="label" name="label" placeholder={KEYS_COPY.labelPlaceholder} maxLength={120} />
            </div>
            <button
              type="button"
              onClick={() => setAdvanced(!advanced)}
              className="text-muted-foreground flex items-center gap-1 self-start text-sm"
              aria-expanded={advanced}
            >
              <ChevronRight className={advanced ? "size-4 rotate-90" : "size-4"} />
              {KEYS_COPY.advanced}
            </button>
            {advanced ? (
              <div className="flex flex-col gap-2">
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="rpm_limit">{KEYS_COPY.rpm}</Label>
                    <Input id="rpm_limit" name="rpm_limit" type="number" min={1} />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="tpm_limit">{KEYS_COPY.tpm}</Label>
                    <Input id="tpm_limit" name="tpm_limit" type="number" min={1} />
                  </div>
                </div>
                <p className="text-muted-foreground text-xs">{KEYS_COPY.limitsHint}</p>
              </div>
            ) : null}
            <ErrorMessage error={add.error} />
            <SheetFooter>
              <Button type="submit" size="lg" className="min-h-10" disabled={add.isPending}>
                {add.isPending ? KEYS_COPY.checking : KEYS_COPY.save}
              </Button>
            </SheetFooter>
          </form>
        ) : null}
      </SheetContent>
    </Sheet>
  )
}
