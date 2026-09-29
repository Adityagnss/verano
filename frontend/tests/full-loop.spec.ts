/**
 * The whole loop on the mock provider: write a prompt, upload a golden set and map its
 * columns, let mock/scripted describe the task and generate test cases, review and approve
 * them, run them on mock/echo, see the results, and let Improve analyze the failures, test
 * 3 candidates and report its holdout verdict. Needs the stack started with
 * VERANO_MOCK_PROVIDER_ENABLED=true (`make e2e`).
 */
import { expect, test } from "@playwright/test"

import { signUp, uniqueEmail } from "./helpers"

const GOLDEN =
  "ticket,expected\nMy card was charged twice,billing\nWhere is my parcel?,shipping\nThe app crashes on start,technical\n"

test("the whole loop runs from keys to an improvement verdict", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "UI flow is engine-independent; covered once")
  test.setTimeout(360_000)
  await signUp(page, uniqueEmail("tests"))
  await page.getByLabel("Project name").fill("Support triage")
  await page.getByRole("button", { name: "Create project" }).click()

  const mock = page.locator('[data-slot="card"]', { hasText: "Mock (development)" })
  await mock.getByRole("button", { name: "Connect" }).click()
  await page.getByRole("button", { name: "Check and save" }).click()
  await expect(page.getByText(/Key saved\. Found \d+ chat models\./)).toBeVisible()
  await page.getByRole("listitem").filter({ hasText: "Mock Scripted" }).getByRole("checkbox").click()
  await page.getByRole("listitem").filter({ hasText: "Mock Echo" }).getByRole("checkbox").click()
  await page.getByRole("button", { name: "Use 2 selected models" }).click()
  await expect(page.getByText("Selection saved.")).toBeVisible()

  await page
    .getByRole("navigation", { name: "Steps" })
    .getByRole("link", { name: /^2 Prompt/ })
    .click()
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

  await page.getByRole("link", { name: "Run" }).click()
  await page.getByRole("checkbox", { name: "Mock Scripted" }).click()
  await expect(page.getByText(/Estimated total/)).toBeVisible()
  await page.getByRole("button", { name: "Start experiment" }).click()
  await page.getByRole("button", { name: "See results" }).click({ timeout: 90_000 })

  await expect(page.getByRole("columnheader", { name: "Quality" })).toBeVisible({ timeout: 30_000 })
  await expect(page.getByRole("cell", { name: "echo" })).toBeVisible()
  await expect(page.getByText("Passed test cases")).toBeVisible()
  await page.getByRole("button", { name: "Next: improve the prompt" }).click()

  await page.getByRole("button", { name: "Find what's failing and suggest fixes" }).click()
  await expect(page.getByText("Echoes the ticket")).toBeVisible({ timeout: 90_000 })
  await expect(page.getByText("strict output rule").first()).toBeVisible({ timeout: 90_000 })
  await expect(page.getByText(/No candidate beat the current prompt|beat the current prompt/)).toBeVisible({
    timeout: 120_000,
  })

  await page.getByRole("link", { name: /Dashboard/ }).click()
  await expect(page.getByRole("heading", { name: "How your prompts and models are doing" })).toBeVisible()
  await expect(page.getByText("Best pass rate (latest)")).toBeVisible()
  await expect(page.getByText("Latest experiment: models side by side")).toBeVisible()
  await expect(page.getByText("Where the money went")).toBeVisible()

  await page.getByRole("link", { name: /Prompt guide/ }).click()
  await expect(page.getByRole("heading", { name: "The one habit: measure first" })).toBeVisible()
})
