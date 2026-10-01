/** A button that copies text to the clipboard and briefly says it worked. */
"use client"

import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // Clipboard access needs a secure page; fall back for plain http on a LAN address.
    const area = document.createElement("textarea")
    area.value = text
    area.setAttribute("readonly", "")
    area.style.position = "fixed"
    area.style.opacity = "0"
    document.body.appendChild(area)
    area.select()
    const ok = document.execCommand("copy")
    area.remove()
    return ok
  }
}

export function CopyButton({
  text,
  label = "Copy",
  doneLabel = "Copied",
  size = "sm",
  variant = "outline",
  notify,
}: {
  text: string | (() => string)
  label?: string
  doneLabel?: string
  size?: "xs" | "sm" | "default"
  variant?: "outline" | "default" | "ghost"
  /** Optional toast shown on success, for copies whose result is not visible on screen. */
  notify?: string
}) {
  const [done, setDone] = useState(false)
  return (
    <Button
      type="button"
      size={size}
      variant={variant}
      onClick={async () => {
        const ok = await copyText(typeof text === "function" ? text() : text)
        if (!ok) {
          toast.error("Could not copy. Select the text and copy it by hand.")
          return
        }
        if (notify) toast.success(notify)
        setDone(true)
        window.setTimeout(() => setDone(false), 2000)
      }}
    >
      {done ? doneLabel : label}
    </Button>
  )
}
