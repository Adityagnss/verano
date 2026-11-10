/**
 * Compare results: the four views. Needs the stack started with VERANO_MOCK_PROVIDER_ENABLED=true (`make e2e`).
 * Signs up, makes a project with the mock provider, runs one test, then walks the tabs.
 */
import { expect, test } from "@playwright/test"

import { goToPage, signUp, uniqueEmail } from "./helpers"

const GOLDEN =
  "ticket,expected\nMy card was charged twice,billing\nWhere is my parcel?,shipping\nThe app crashes on start,technical\n"

test("compare results: summary, compare models, answers, runs and details", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "UI flow is engine-independent; covered once")
  test.setTimeout(360_000)
  await signUp(page, uniqueEmail("results"))
  await page.getByLabel("Project name").fill("Results tour")
  await page.getByRole("button", { name: "Create project" }).click()
  await expect(page).toHaveURL(/\/projects\/[^/]+\//)

  const mock = page.locator('[data-slot="card"]', { hasText: "Mock (development)" })
  await mock.getByRole("button", { name: "Connect" }).click()
  await page.getByRole("button", { name: "Check and save" }).click()
  await expect(page.getByText(/Key saved\. Found \d+ chat models\./)).toBeVisible()
  await page.getByRole("listitem").filter({ hasText: "Mock Scripted" }).getByRole("checkbox").click()
  await page.getByRole("listitem").filter({ hasText: "Mock Echo" }).getByRole("checkbox").click()
  await page.getByRole("button", { name: "Use 2 selected models" }).click()
  await expect(page.getByText("Selection saved.")).toBeVisible()

  await goToPage(page, /^Write your prompt/)
  await page.getByLabel("Prompt name").fill("Triage")
  await page.getByLabel("System prompt").fill("Classify the support ticket. Reply with one word.")
  await page.getByRole("button", { name: "Save prompt" }).click()
  await expect(page).toHaveURL(/\/data$/)

  const tickets = ["My card was charged twice", "Where is my parcel?", "The app crashes on start"]
  await page.getByTestId("upload-inputs").setInputFiles(
    tickets.map((text, i) => ({
      name: `case${i + 1}.txt`,
      mimeType: "text/plain",
      buffer: Buffer.from(text),
    })),
  )
  await expect(page.getByText("case3.txt", { exact: true })).toBeVisible()
  await page.getByTestId("upload-golden").setInputFiles({
    name: "golden.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(GOLDEN),
  })
  await page.getByRole("button", { name: "Check entries" }).click()
  await page.getByRole("button", { name: "Import 3 answers" }).click()
  await expect(page.getByText("3 answers matched").first()).toBeVisible()
  await page.getByRole("button", { name: "Next: test cases" }).click()

  // the writer model is a suggested line with a Change button since the review of the Test Cases step
  await page.locator("button#generator").click()
  await page.locator("select#generator").selectOption("scripted")
  await page.getByRole("button", { name: "Describe the task" }).click()
  await expect(page.getByLabel("Goal")).toHaveValue("Classify support tickets into categories")
  await page.getByRole("button", { name: "Confirm task" }).click()
  await page.getByRole("checkbox", { name: "Use only my files (no generation)" }).click()
  await page.getByRole("button", { name: "Generate test cases" }).click()

  await expect(page.getByRole("button", { name: "Approve test cases" })).toBeVisible({ timeout: 90_000 })
  const approveAll = page.getByRole("button", { name: /^Approve \d+ drafts$/ })
  await expect(page.getByText("Golden").first()).toBeVisible()
  while ((await approveAll.count()) > 0) {
    const before = await approveAll.count()
    await approveAll.first().click()
    await expect(approveAll).toHaveCount(before - 1)
  }
  await page.getByRole("button", { name: "Approve test cases" }).click()
  await expect(page.getByText("Test cases approved (version 1)").first()).toBeVisible()
  await expect(page.getByText(/held back to check the result/)).toBeVisible()

  await goToPage(page, /^Run the test/)
  await page.getByRole("button", { name: "Start experiment" }).click()
  await page.getByRole("button", { name: "See results" }).click({ timeout: 90_000 })

  await expect(page.getByRole("heading", { name: "Compare results", level: 1 })).toBeVisible()
  await expect(page.getByRole("tab", { name: "Summary" })).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId("winner-card")).toBeVisible({ timeout: 30_000 })
  await expect(page.getByRole("link", { name: "Improve the prompt" })).toBeVisible()

  await page.getByRole("tab", { name: "Compare models" }).click()
  await expect(page.getByRole("columnheader", { name: "Quality" })).toBeVisible()
  await expect(page.getByText("Passed test cases")).toBeVisible()

  await page.getByRole("tab", { name: "Answers" }).click()
  await expect(page.getByText("Only cases with a failure")).toBeVisible()

  await page.getByRole("tab", { name: "Runs and details" }).click()
  await expect(page.getByRole("button", { name: "Export CSV" })).toBeVisible()

  await goToPage(page, /^Compare results/)
  await expect(page.getByRole("tab", { name: "Summary" })).toBeVisible()
})
