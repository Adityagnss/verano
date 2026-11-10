/**
 * The whole loop on the mock provider: write a prompt, upload a golden set and map its
 * columns, let mock/scripted describe the task and generate test cases, review and approve
 * them, run them on mock/echo, see the results, and let Improve analyze the failures, test
 * 3 candidates and report its holdout verdict. Needs the stack started with
 * VERANO_MOCK_PROVIDER_ENABLED=true (`make e2e`).
 */
import { expect, test } from "@playwright/test"

import { chooseTheme, goToPage, openAccountMenu, signUp, uniqueEmail } from "./helpers"

const GOLDEN =
  "ticket,expected\nMy card was charged twice,billing\nWhere is my parcel?,shipping\nThe app crashes on start,technical\n"

test("the whole loop runs from keys to an improvement verdict", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "UI flow is engine-independent; covered once")
  test.setTimeout(360_000)
  await signUp(page, uniqueEmail("tests"))
  await page.getByLabel("Project name").fill("Support triage")
  await page.getByRole("button", { name: "Create project" }).click()
  await expect(page).toHaveURL(/\/projects\/[^/]+\//)
  const project = new URL(page.url()).pathname.split("/").slice(0, 3).join("/")

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
  // both ticked models run by default; the per-model table moved under Expert settings
  await expect(page.getByText("What will run")).toBeVisible()
  await page.getByRole("button", { name: "Start experiment" }).click()
  await page.getByRole("button", { name: "See results" }).click({ timeout: 90_000 })

  await page.getByRole("tab", { name: "Compare models" }).click({ timeout: 30_000 })
  await expect(page.getByRole("columnheader", { name: "Quality" })).toBeVisible({ timeout: 30_000 })
  await expect(page.getByRole("cell", { name: "echo" })).toBeVisible()
  await expect(page.getByText("Passed test cases")).toBeVisible()
  await page.getByRole("button", { name: "Next: improve the prompt" }).click()

  await page.getByRole("button", { name: "Find what's failing and suggest fixes" }).click()
  await expect(page.getByText("Echoes the ticket")).toBeVisible({ timeout: 90_000 })
  await expect(page.getByText("strict output rule").first()).toBeVisible({ timeout: 90_000 })
  await expect(page.getByText(/Not proven: only \d+ held-back cases were judged/)).toBeVisible({
    timeout: 120_000,
  })

  await goToPage(page, /^Trends/)
  await expect(page.getByRole("heading", { name: "How your prompts and models are doing" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Is the prompt getting better?" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "What this tells you" })).toBeVisible()
  await expect(page.getByText("Where the money went")).toBeVisible()

  await goToPage(page, /^History/)
  await expect(page.getByRole("heading", { name: "Logbook", level: 2 })).toBeVisible()
  await expect(page.getByRole("cell", { name: "echo" }).first()).toBeVisible()
  await page.getByRole("row", { name: "Open this answer" }).first().click()
  await expect(page.getByText("Golden answer and model answer")).toBeVisible()
  await page.keyboard.press("Escape")
  await page.getByRole("tab", { name: /Analysis/ }).click()
  await expect(page.getByText("Pass rate by model and prompt version")).toBeVisible()
  await page.getByRole("tab", { name: /Model calls/ }).click()
  await expect(page.getByRole("cell", { name: "Running your test cases" }).first()).toBeVisible()

  await goToPage(page, /^Prompting guide/)
  await expect(page.getByRole("heading", { name: "The one habit: measure first" })).toBeVisible()

  await openAccountMenu(page)
  await page.getByRole("menuitem", { name: "Usage and spend" }).click()
  await expect(page.getByRole("heading", { name: "Activity", level: 1 })).toBeVisible()
  await expect(page.getByText("Top API keys")).toBeVisible()
  await expect(
    page
      .getByText("mock no key needed")
      .or(page.getByText(/^mock ending/))
      .first(),
  ).toBeVisible()
  await page.getByRole("tab", { name: "Explore" }).click()
  await expect(page.getByRole("cell", { name: "echo" }).first()).toBeVisible()
  await page.getByRole("tab", { name: "Guardrails" }).click()
  await expect(page.getByText("What stops spending")).toBeVisible()

  // Prompt versions: save version 2, test it, compare it with version 1 on the Dashboard
  await page.goto(`${project}/prompt`)
  await page.getByLabel("System prompt").fill("Classify the support ticket. Reply with one lowercase word.")
  await page.getByRole("button", { name: "Save new version" }).click()
  await expect(page).toHaveURL(/\/data$/)
  await page.goto(`${project}/run`)
  await expect(page.getByLabel("Prompt version to test")).toContainText("Version 2 (latest)")
  await expect(page.getByLabel("Prompt version to test")).toContainText("Version 1")
  await expect(page.getByRole("radio", { name: /Repeatable/ })).toBeChecked()
  await expect(page.getByText("What will run")).toBeVisible()
  await page.getByRole("button", { name: "Start experiment" }).click()
  await page.getByRole("button", { name: "See results" }).click({ timeout: 90_000 })
  await page.getByRole("tab", { name: "Compare models" }).click({ timeout: 30_000 })
  await expect(page.getByRole("columnheader", { name: "Quality" })).toBeVisible({ timeout: 30_000 })
  await page.goto(`${project}/dashboard`)
  await expect(page.getByText("All versions at a glance")).toBeVisible()
  await expect(page.getByRole("columnheader", { name: "V1" })).toBeVisible()
  await expect(page.getByRole("columnheader", { name: "V2" })).toBeVisible()
  // Version 1 was scored again above with edited criteria, so the honest answer here is that the two runs
  // can't be compared until one is scored like the other; with the same checks it shows the comparison.
  await expect(page.getByText(/cases? fixed|scored with different checks/).first()).toBeVisible({
    timeout: 30_000,
  })

  // Light and dark themes
  await chooseTheme(page, "Dark")
  await expect(page.locator("html")).toHaveClass(/dark/)
  await chooseTheme(page, "Light")
  await expect(page.locator("html")).not.toHaveClass(/dark/)
})
