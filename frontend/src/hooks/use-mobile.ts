import { useSyncExternalStore } from "react"

/** Below this width the sidebar is a drawer (Sheet); from here up it is a rail or full sidebar. */
const MOBILE_BREAKPOINT = 1024

function subscribe(onChange: () => void) {
  window.addEventListener("resize", onChange)
  return () => window.removeEventListener("resize", onChange)
}

export function useIsMobile() {
  return useSyncExternalStore(
    subscribe,
    () => window.innerWidth < MOBILE_BREAKPOINT,
    () => false,
  )
}
