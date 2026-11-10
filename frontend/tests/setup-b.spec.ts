/**
 * Approve test cases, Run the test and Improve the prompt: opens each page on a desktop and a phone width and checks
 * the new headings and that nothing scrolls sideways. Needs the stack started with
 * VERANO_MOCK_PROVIDER_ENABLED=true (`make e2e`).
 */
import { expect, test } from "@playwright/test"

import { goToPage, signUp, uniqueEmail } from "./helpers"

test("test cases, run and improve pages open cleanly at desktop and phone width", async ({
  page,
  browserName,
}) => {
  test.skip(browserName !== "chromium", "UI flow is engine-independent; covered once")
  test.setTimeout(120_000)
  await signUp(page, uniqueEmail("setupb"))
  await page.getByLabel("Project name").fill("Setup B")
  await page.getByRole("button", { name: "Create project" }).click()
  await expect(page).toHaveURL(/\/projects\/[^/]+\//)

  const mock = page.locator('[data-slot="card"]', { hasText: "Mock (development)" })
  await mock.getByRole("button", { name: "Connect" }).click()
  await page.getByRole("button", { name: "Check and save" }).click()
  await expect(page.getByText(/Key saved\. Found \d+ chat models\./)).toBeVisible()
  await page.getByRole("listitem").filter({ hasText: "Mock Echo" }).getByRole("checkbox").click()
  await page.getByRole("button", { name: "Continue with 1 model" }).click()
  await expect(page.getByText("Selection saved.")).toBeVisible()

  await goToPage(page, /^Write your prompt/)
  await page.getByLabel("Prompt name").fill("Triage")
  await page.getByLabel("System prompt").fill("Classify the support ticket. Reply with one word.")
  await page.getByRole("button", { name: "Save prompt" }).click()
  await expect(page).toHaveURL(/\/data$/)

  const pages: [RegExp, string][] = [
    [/^Approve test cases/, "Approve test cases"],
    [/^Run the test/, "Run the test"],
    [/^Improve the prompt/, "Improve the prompt"],
  ]
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 900 })
    for (const [link, heading] of pages) {
      await goToPage(page, link)
      await expect(page.getByText(heading, { exact: true }).first()).toBeVisible()
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )
      expect(overflow).toBeLessThanOrEqual(1)
    }
  }
})
