/** Which prompt to test, when a project has several. Shows nothing for a project with one prompt. */
"use client"

import { useQuery } from "@tanstack/react-query"

import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/select"
import { api, call } from "@/lib/api/client"

export function usePrompts(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "prompts-all"],
    queryFn: async () =>
      (
        await call(() =>
          api.GET("/api/v1/projects/{project_id}/prompts", {
            params: { path: { project_id: projectId }, query: { limit: 50 } },
          }),
        )
      ).items,
  })
}

export const CHOOSER_COPY = {
  label: "Prompt to test",
  hint: "This project has more than one prompt. The experiment is run on the one you pick, and results are only compared within the same prompt.",
}

export function PromptChooser({
  projectId,
  value,
  onChange,
  id = "prompt-choice",
}: {
  projectId: string
  /** The chosen prompt's id; "" means the newest one. */
  value: string
  onChange: (promptId: string) => void
  id?: string
}) {
  const prompts = usePrompts(projectId)
  const items = prompts.data ?? []
  if (items.length < 2) return null
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{CHOOSER_COPY.label}</Label>
      <NativeSelect id={id} value={value} onChange={(e) => onChange(e.target.value)} className="h-9 max-w-md">
        {items.map((p, i) => (
          <option key={p.id} value={i === 0 ? "" : p.id}>
            {p.name}
            {i === 0 ? " (newest)" : ""}
          </option>
        ))}
      </NativeSelect>
      <p className="text-text-muted text-xs">{CHOOSER_COPY.hint}</p>
    </div>
  )
}
