/** The blind review switch: hides the judge's verdicts and scores so a person can label answers without being swayed. */
"use client"

import { EyeOff } from "lucide-react"

import { Checkbox } from "@/components/ui/checkbox"

import { BLIND_COPY } from "../screens-copy"

export function BlindToggle({ blind, onChange }: { blind: boolean; onChange: (blind: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm" title={BLIND_COPY.explain}>
      <Checkbox
        checked={blind}
        onCheckedChange={(checked) => onChange(checked)}
        aria-describedby="blind-explain"
      />
      {BLIND_COPY.label}
    </label>
  )
}

export function BlindNotice() {
  return (
    <p
      id="blind-explain"
      className="bg-info-soft text-info-strong flex items-start gap-2 rounded-lg p-3 text-sm"
      role="status"
    >
      <EyeOff className="mt-0.5 size-4 shrink-0" />
      <span>{BLIND_COPY.explain}</span>
    </p>
  )
}
