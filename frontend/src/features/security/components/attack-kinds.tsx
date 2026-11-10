/** The attack kinds as expandable items with a checkbox each, plus select all / none. */
"use client"

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { StatusBadge } from "@/components/common/status-badge"
import type { AttackFamilyOut } from "@/lib/api/types"

import { kindNotes } from "../domain"

export function AttackKinds({
  families,
  selected,
  onChange,
}: {
  families: AttackFamilyOut[]
  selected: Set<string>
  onChange: (next: Set<string>) => void
}) {
  const toggle = (id: string, on: boolean) => {
    const next = new Set(selected)
    if (on) next.add(id)
    else next.delete(id)
    onChange(next)
  }
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-text-secondary mr-auto text-sm" aria-live="polite">
          {selected.size} of {families.length} kinds selected
        </p>
        <Button
          variant="outline"
          size="sm"
          className="min-h-10"
          onClick={() => onChange(new Set(families.map((f) => f.id)))}
        >
          Select all
        </Button>
        <Button variant="outline" size="sm" className="min-h-10" onClick={() => onChange(new Set())}>
          Select none
        </Button>
      </div>
      <Accordion multiple className="bg-card ring-border rounded-lg px-3 ring-1">
        {families.map((f) => {
          const notes = kindNotes(f.id, f.description)
          return (
            <AccordionItem key={f.id} value={f.id}>
              <div className="flex items-start gap-3">
                <div className="flex min-h-10 items-center">
                  <Checkbox
                    aria-label={`Test: ${f.title}`}
                    checked={selected.has(f.id)}
                    onCheckedChange={(on) => toggle(f.id, on)}
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <AccordionTrigger className="min-h-10 items-center">
                    <span className="flex min-w-0 flex-wrap items-center gap-2">
                      <span>{f.title}</span>
                      <StatusBadge>OWASP {f.owasp}</StatusBadge>
                    </span>
                  </AccordionTrigger>
                </div>
              </div>
              <AccordionContent className="pl-7">
                <dl className="text-text-secondary flex flex-col gap-2 text-sm">
                  <div>
                    <dt className="text-foreground font-medium">What the attacker tries</dt>
                    <dd>{f.description}</dd>
                  </div>
                  <div>
                    <dt className="text-foreground font-medium">An example</dt>
                    <dd>“{notes.sample}”</dd>
                  </div>
                  <div>
                    <dt className="text-foreground font-medium">A safe answer</dt>
                    <dd>{f.safe_behaviour}</dd>
                  </div>
                  <div>
                    <dt className="text-foreground font-medium">Why it matters</dt>
                    <dd>{notes.why}</dd>
                  </div>
                </dl>
              </AccordionContent>
            </AccordionItem>
          )
        })}
      </Accordion>
    </div>
  )
}
