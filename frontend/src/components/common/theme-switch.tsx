/**
 * Light, dark or the system's choice, as one icon button with a small menu. The icon shows the
 * current choice; the choice is remembered in the browser by next-themes.
 */
"use client"

import { Check, Monitor, Moon, Sun } from "lucide-react"
import { useTheme } from "next-themes"
import { useSyncExternalStore } from "react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

const CHOICES = [
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
  { value: "system", label: "Same as your system", Icon: Monitor },
] as const

const subscribe = () => () => undefined

export function ThemeSwitch() {
  const { theme, setTheme } = useTheme()
  // The theme is only known in the browser; render a placeholder on the server so the markup matches.
  const mounted = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  )
  const active = CHOICES.find((choice) => choice.value === theme) ?? CHOICES[2]
  if (!mounted) return <span className="size-10" aria-hidden />
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button variant="ghost" className="size-10" aria-label={`Color theme: ${active.label}`}>
            <active.Icon aria-hidden />
          </Button>
        }
      />
      <DropdownMenuContent align="end" className="w-56 min-w-56">
        {CHOICES.map(({ value, label, Icon }) => (
          <DropdownMenuItem
            key={value}
            role="menuitemradio"
            aria-checked={theme === value}
            className="min-h-10"
            onClick={() => setTheme(value)}
          >
            <Icon aria-hidden />
            {label}
            {theme === value ? <Check aria-hidden className="ml-auto" /> : null}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
