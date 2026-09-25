/**
 * Playwright configuration for browser tests against the running stack (`make e2e`
 * starts it). Everything goes through Caddy at E2E_BASE_URL over plain HTTP, exactly as a
 * local user would, and runs in Chromium, WebKit (Safari's engine) and Firefox, which
 * is how the refresh cookie is checked in every engine.
 */
import { defineConfig, devices } from "@playwright/test"

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
  ],
})
