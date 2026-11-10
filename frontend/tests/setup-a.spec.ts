/**
 * Connect models, Write your prompt, Add examples on the mock provider. Needs the stack started
 * with VERANO_MOCK_PROVIDER_ENABLED=true (`make e2e` does this).
 */
import { expect, test } from "@playwright/test"

import { goToPage, signUp, uniqueEmail } from "./helpers"

test("connect a model, write a prompt, then add examples", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "UI flow is engine-independent; covered once")
  await signUp(page, uniqueEmail("setupa"))
  await page.getByLabel("Project name").fill("Support triage")
  await page.getByRole("button", { name: "Create project" }).click()
  await expect(page.getByRole("heading", { level: 1, name: "Connect models" })).toBeVisible()

  const mock = page.locator('[data-slot="card"]', { hasText: "Mock (development)" })
  await mock.getByRole("button", { name: "Connect" }).click()
  await page.getByRole("button", { name: "Check and save" }).click()
  await expect(page.getByText(/Key saved\. Found \d+ chat models\./)).toBeVisible()
  await expect(mock.getByText(/^Connected/)).toBeVisible()
  await page.getByRole("listitem").filter({ hasText: "Mock Echo" }).getByRole("checkbox").click()
  await expect(page.getByText("1 model selected").first()).toBeVisible()
  await page.getByRole("button", { name: "Continue with 1 model" }).click()
  await expect(page.getByRole("heading", { level: 1, name: "Write your prompt" })).toBeVisible()

  await page.getByLabel("System prompt").fill("Classify the support ticket. Reply with one word.")
  await page.getByRole("button", { name: "Save prompt" }).click()
  await expect(page.getByRole("heading", { level: 1, name: "Add examples" })).toBeVisible()

  await page.getByRole("checkbox", { name: "Input files" }).click()
  await page.getByRole("button", { name: "Next", exact: true }).click()
  await page.getByTestId("upload-inputs").setInputFiles({
    name: "case1.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Where is my parcel?"),
  })
  await expect(page.getByText("case1.txt", { exact: true }).first()).toBeVisible()
  await page.getByRole("button", { name: "Next", exact: true }).click()
  // the next step waits while the file is still being read, so keep trying until it moves on
  await expect(async () => {
    await page.getByRole("button", { name: "Next", exact: true }).click()
    await expect(page.getByRole("button", { name: "Next: test cases" })).toBeVisible({ timeout: 1000 })
  }).toPass({ timeout: 20000 })
  await page.getByRole("button", { name: "Next: test cases" }).click()
  await expect(page).toHaveURL(/\/tests$/)

  await goToPage(page, /^Add examples/)
  await expect(page.getByRole("heading", { level: 1, name: "Add examples" })).toBeVisible()
})
