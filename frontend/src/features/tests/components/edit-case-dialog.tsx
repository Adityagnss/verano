/** Edit one test case: its inputs, correct answer or grading criteria, and category. Saving counts as reviewing it. */
"use client"

import type { UseMutationResult } from "@tanstack/react-query"
import { type FormEvent, useState } from "react"

import { ErrorMessage } from "@/components/common/error-message"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import type { ItemOut, ItemUpdate } from "@/lib/api/types"

import { TESTS_COPY } from "../copy"

type Save = UseMutationResult<ItemOut, Error, { itemId: string; body: ItemUpdate }>

function CaseForm({ item, onClose, save }: { item: ItemOut; onClose: () => void; save: Save }) {
  const [inputs, setInputs] = useState<Record<string, string>>(() =>
    Object.fromEntries(Object.entries(item.inputs).map(([k, v]) => [k, String(v)])),
  )
  const [expected, setExpected] = useState(item.expected_output ?? "")
  const [rubric, setRubric] = useState((item.rubric ?? []).map(String).join("\n"))
  const [category, setCategory] = useState(item.category)

  async function submit(event: FormEvent) {
    event.preventDefault()
    const criteria = rubric
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
    await save.mutateAsync({
      itemId: item.id,
      body: {
        inputs,
        expected_output: expected.trim() || null,
        rubric: criteria.length ? criteria : null,
        category: category.trim() || item.category,
      },
    })
    onClose()
  }

  return (
    <form onSubmit={(e) => void submit(e).catch(() => undefined)} className="flex flex-col gap-4">
      <DialogHeader>
        <DialogTitle>{TESTS_COPY.editTitle}</DialogTitle>
      </DialogHeader>
      {Object.keys(inputs).map((name) => (
        <div key={name} className="flex flex-col gap-1.5">
          <Label htmlFor={`input-${name}`}>{name}</Label>
          <Textarea
            id={`input-${name}`}
            rows={4}
            className="font-mono"
            value={inputs[name]}
            onChange={(e) => setInputs({ ...inputs, [name]: e.target.value })}
          />
        </div>
      ))}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="expected">{TESTS_COPY.expected}</Label>
        <Input id="expected" value={expected} onChange={(e) => setExpected(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="rubric">{TESTS_COPY.rubric}</Label>
        <Textarea id="rubric" rows={3} value={rubric} onChange={(e) => setRubric(e.target.value)} />
      </div>
      <div className="flex max-w-xs flex-col gap-1.5">
        <Label htmlFor="category">{TESTS_COPY.category}</Label>
        <Input id="category" value={category} onChange={(e) => setCategory(e.target.value)} />
      </div>
      <ErrorMessage error={save.error} />
      <DialogFooter>
        <Button type="submit" disabled={save.isPending}>
          {TESTS_COPY.save}
        </Button>
      </DialogFooter>
    </form>
  )
}

export function EditCaseDialog({
  item,
  onClose,
  save,
}: {
  item: ItemOut | null
  onClose: () => void
  save: Save
}) {
  return (
    <Dialog open={item !== null} onOpenChange={(open) => (open ? undefined : onClose())}>
      <DialogContent className="sm:max-w-2xl">
        {item ? <CaseForm key={item.id} item={item} onClose={onClose} save={save} /> : null}
      </DialogContent>
    </Dialog>
  )
}
