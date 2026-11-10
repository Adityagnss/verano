/**
 * The "..." menu on a project card: rename it, or delete it with everything in it. Deleting asks first and says
 * what is lost; a name that another project already uses is refused with the server's message.
 */
"use client"

import { MoreHorizontal, Pencil, Trash2 } from "lucide-react"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"

import { ErrorMessage } from "@/components/common/error-message"
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

import { useDeleteProject, useRenameProject } from "../hooks"

export function ProjectActions({ id, name }: { id: string; name: string }) {
  const [renaming, setRenaming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [draft, setDraft] = useState(name)
  const rename = useRenameProject(id)
  const remove = useDeleteProject(id)

  function submit(event: FormEvent) {
    event.preventDefault()
    rename.mutate(draft.trim(), {
      onSuccess: () => {
        setRenaming(false)
        toast.success("Project renamed.")
      },
    })
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button variant="ghost" size="icon" className="size-10" aria-label={`Actions for ${name}`}>
              <MoreHorizontal aria-hidden />
            </Button>
          }
        />
        <DropdownMenuContent align="end">
          <DropdownMenuItem
            className="min-h-10"
            onClick={() => {
              setDraft(name)
              rename.reset()
              setRenaming(true)
            }}
          >
            <Pencil aria-hidden />
            Rename
          </DropdownMenuItem>
          <DropdownMenuItem
            className="text-destructive min-h-10"
            onClick={() => {
              remove.reset()
              setDeleting(true)
            }}
          >
            <Trash2 aria-hidden />
            Delete project
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={renaming} onOpenChange={setRenaming}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename project</DialogTitle>
            <DialogDescription>Each project needs its own name.</DialogDescription>
          </DialogHeader>
          <form onSubmit={submit} className="flex flex-col gap-3">
            <Label htmlFor={`rename-${id}`}>Project name</Label>
            <Input
              id={`rename-${id}`}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              maxLength={200}
              className="h-10"
              autoFocus
            />
            <ErrorMessage error={rename.error} />
            <Button type="submit" size="lg" className="min-h-10" disabled={!draft.trim() || rename.isPending}>
              {rename.isPending ? "Saving..." : "Save name"}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog open={deleting} onOpenChange={setDeleting}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {name}?</AlertDialogTitle>
            <AlertDialogDescription>
              This removes the project and everything in it: prompts, test cases, runs, results and saved
              keys. It cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <ErrorMessage error={remove.error} />
          <AlertDialogFooter>
            <AlertDialogCancel className="min-h-10">Keep project</AlertDialogCancel>
            <Button
              variant="destructive"
              className="min-h-10"
              disabled={remove.isPending}
              onClick={() =>
                remove.mutate(undefined, {
                  onSuccess: () => {
                    setDeleting(false)
                    toast.success("Project deleted.")
                  },
                })
              }
            >
              {remove.isPending ? "Deleting..." : "Delete project"}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
