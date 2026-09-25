/**
 * The Keys step on the mock provider: create a project, connect a provider, see its
 * chat models with prices, pick one and save the choice. Needs the stack started with
 * VERANO_MOCK_PROVIDER_ENABLED=true (`make e2e` does this). Runs in one engine; the
 * session test already covers every engine.
 */
import { expect, test } from "@playwright/test"

import { signUp, uniqueEmail } from "./helpers"

test("a new project can connect a provider and choose a model to test", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "UI flow is engine-independent; covered once")
  await signUp(page, uniqueEmail("keys"))

  await page.getByLabel("Project name").fill("Support triage")
  await page.getByRole("button", { name: "Create project" }).click()
  await expect(page).toHaveURL(/\/projects\/[0-9a-f-]+\/keys$/)
  await expect(page.getByRole("heading", { name: "Connect your model providers" })).toBeVisible()

  const mock = page.locator('[data-slot="card"]', { hasText: "Mock (development)" })
  await mock.getByRole("button", { name: "Connect" }).click()
  await page.getByRole("button", { name: "Check and save" }).click()
  await expect(page.getByText(/Key saved\. Found \d+ chat models\./)).toBeVisible()

  const echo = page.getByRole("listitem").filter({ hasText: "Mock Echo" })
  await expect(echo).toContainText("$0.50 / $1.50")
  await echo.getByRole("checkbox").click()
  await page.getByRole("button", { name: "Use 1 selected model" }).click()
  await expect(page.getByText("Selection saved.")).toBeVisible()

  await page.reload()
  await expect(
    page.getByRole("listitem").filter({ hasText: "Mock Echo" }).getByRole("checkbox"),
  ).toBeChecked()
})
