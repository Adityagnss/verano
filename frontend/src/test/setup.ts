/** Setup for jsdom tests: jest-dom matchers, cleanup, and the browser APIs jsdom lacks. */
import "@testing-library/jest-dom/vitest"

import { cleanup } from "@testing-library/react"
import { afterEach, vi } from "vitest"

import { setViewport } from "./viewport"

class NoopObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

vi.stubGlobal("ResizeObserver", NoopObserver)
vi.stubGlobal("IntersectionObserver", NoopObserver)
Element.prototype.scrollIntoView = () => {}
setViewport(1440)

afterEach(() => {
  cleanup()
  try {
    window.localStorage.clear()
  } catch {
    /* ignore */
  }
  setViewport(1440)
})
