/** Live traffic: the guided path, connecting an app (token and snippets), and the four tabs. */
import { expect, test } from "@playwright/test"

import { goToPage, signUp, uniqueEmail } from "./helpers"

test("live traffic explains itself and lets you connect an app", async ({ page }) => {
  await signUp(page, uniqueEmail("traffic"))
  await page.getByLabel("Project name").fill("Traffic demo")
  await page.getByRole("button", { name: "Create project" }).click()
  await expect(page).toHaveURL(/\/projects\/[^/]+\//)

  await goToPage(page, /^Live traffic/)
  await expect(page.getByRole("heading", { level: 1, name: "Live traffic" })).toBeVisible()
  await expect(page.getByRole("list", { name: "How to get started" })).toBeVisible()
  await expect(page.getByText("Example, not real traffic")).toBeVisible()

  // the primary action opens the Connect tab
  await page.getByRole("button", { name: "Connect your app" }).first().click()
  await expect(page.getByRole("tab", { name: "Connect", exact: true })).toHaveAttribute(
    "aria-selected",
    "true",
  )
  await page.locator("#token-name").fill("my-app")
  await page.getByRole("button", { name: "Create token" }).click()
  await expect(page.getByRole("status").filter({ hasText: /once/i })).toBeVisible()
  await expect(page.getByText(/OpenInference and OpenLLMetry only/)).toBeVisible()
  await page.getByRole("tab", { name: "Node" }).click()
  await expect(page.getByText("OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer").first()).toBeVisible()

  // the other tabs open without errors
  for (const name of ["Live scores", "Alerts", "Traffic"]) {
    await page.getByRole("tab", { name, exact: true }).click()
    await expect(page.getByRole("tab", { name, exact: true })).toHaveAttribute("aria-selected", "true")
  }
  await page.getByRole("button", { name: "Import a file" }).click()
  await expect(page.getByRole("dialog")).toBeVisible()
})
