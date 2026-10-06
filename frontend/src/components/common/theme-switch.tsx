/**
 * Light, dark or the system's choice. Three small buttons so the current choice is always visible; the
 * choice is remembered in the browser by next-themes.
 */
"use client"

import { Monitor, Moon, Sun } from "lucide-react"
import { useTheme } from "next-themes"
import { useSyncExternalStore } from "react"

import { cn } from "@/lib/utils"

const CHOICES = [
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
  { value: "system", label: "Same as your system", Icon: Monitor },
] as const

const subscribe = () => () => undefined

export function ThemeSwitch() {
  const { theme, setTheme } = useTheme()
  // The theme is only known in the browser; render nothing on the server so the markup matches.
  const mounted = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  )
  if (!mounted) return <span className="h-8 w-[5.75rem]" aria-hidden />
  return (
    <div
      role="radiogroup"
      aria-label="Color theme"
      className="bg-subtle ring-border flex rounded-lg p-0.5 ring-1"
    >
      {CHOICES.map(({ value, label, Icon }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={theme === value}
          title={label}
          aria-label={label}
          onClick={() => setTheme(value)}
          className={cn(
            "text-text-secondary hover:text-foreground focus-visible:ring-ring/50 flex size-7 items-center justify-center rounded-md transition-colors focus-visible:ring-2 focus-visible:outline-none",
            theme === value && "bg-card text-foreground shadow-sm",
          )}
        >
          <Icon className="size-4" aria-hidden />
        </button>
      ))}
    </div>
  )
}
