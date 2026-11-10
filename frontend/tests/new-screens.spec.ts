/**
 * Opens every screen added since Phase 6 and fails on a crash, a console error, a failed request or an error
 * message on the page. Needs the stack started with VERANO_MOCK_PROVIDER_ENABLED=true (`make e2e`). Set
 * SCREENSHOT_DIR to keep a picture of each screen.
 */
import { expect, test, type Page } from "@playwright/test"

import { signUp, uniqueEmail } from "./helpers"

const ERROR_TEXT = /application error|something went wrong|unhandled runtime error|internal server error/i

const PROJECT_SCREENS = [
  "apps",
  "review",
  "traffic",
  "security",
  "improve",
  "tests",
  "results",
  "logbook",
  "dashboard",
  "guide",
  "keys",
  "prompt",
  "data",
  "run",
]
const WORKSPACE_SCREENS = ["/workspace", "/tokens", "/activity"]

interface Problems {
  console: string[]
  requests: string[]
}

function watch(page: Page): Problems {
  const problems: Problems = { console: [], requests: [] }
  page.on("pageerror", (error) => problems.console.push(`page error: ${error.message}`))
  page.on("console", (message) => {
    if (message.type() === "error" && !/status of 404/.test(message.text()))
      problems.console.push(message.text())
  })
  page.on("response", (response) => {
    const url = response.url()
    if (url.includes("/api/") && response.status() >= 500)
      problems.requests.push(`${response.status()} ${url}`)
    if (url.includes("/api/") && response.status() === 404 && !/\/(me|latest|current|settings)/.test(url)) {
      problems.requests.push(`404 ${url}`)
    }
  })
  return problems
}

async function look(page: Page, name: string, problems: Problems, report: string[]): Promise<void> {
  await page.waitForLoadState("networkidle")
  const body = (await page.locator("body").innerText()).slice(0, 4000)
  if (ERROR_TEXT.test(body)) report.push(`${name}: the page shows an error message`)
  if ((await page.locator("main, [role=main], h1, h2").count()) === 0)
    report.push(`${name}: nothing was drawn`)
  const dir = process.env.SCREENSHOT_DIR
  if (dir) await page.screenshot({ path: `${dir}/${name}.png`, fullPage: true })
  for (const line of problems.requests) report.push(`${name}: failed call ${line}`)
  for (const line of problems.console) report.push(`${name}: console ${line.slice(0, 200)}`)
}

test("every screen added since Phase 6 opens without errors", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "the screens are engine-independent; covered once")
  test.setTimeout(300_000)
  const problems = watch(page)
  const report: string[] = []
  await signUp(page, uniqueEmail("screens"))
  await page.getByLabel("Project name").fill("Screens check")
  await page.getByRole("button", { name: "Create project" }).click()
  await expect(page).toHaveURL(/\/projects\/[^/]+\//)
  const project = new URL(page.url()).pathname.split("/").slice(0, 3).join("/")

  let loads = 0
  // every full page load asks for a fresh session, and sign-in calls are limited to 20 a minute per IP
  const pace = async () => {
    if (++loads % 8 === 0) await page.waitForTimeout(45_000)
  }
  for (const screen of PROJECT_SCREENS) {
    await pace()
    problems.console.length = 0
    problems.requests.length = 0
    await page.goto(`${project}/${screen}`)
    await look(page, `project-${screen}`, problems, report)
  }
  for (const path of WORKSPACE_SCREENS) {
    await pace()
    problems.console.length = 0
    problems.requests.length = 0
    await page.goto(path)
    await look(page, `workspace${path.replace(/\//g, "-")}`, problems, report)
  }
  expect(report, "problems found while opening the screens").toEqual([])
})

test("a token, a spending limit and an ingest token can be made and removed", async ({
  page,
  browserName,
}) => {
  test.skip(browserName !== "chromium", "the screens are engine-independent; covered once")
  test.setTimeout(120_000)
  await signUp(page, uniqueEmail("actions"))
  await page.getByLabel("Project name").fill("Actions check")
  await page.getByRole("button", { name: "Create project" }).click()
  await expect(page).toHaveURL(/\/projects\/[^/]+\//)
  const project = new URL(page.url()).pathname.split("/").slice(0, 3).join("/")

  // an API token is shown once, listed as read only, and stops working when revoked
  await page.goto("/tokens")
  await page.getByPlaceholder("for example ci").fill("ci")
  await page.getByRole("button", { name: "Make token" }).click()
  const shown = page.getByRole("status").filter({ hasText: "shown only now" })
  await expect(shown).toBeVisible()
  await expect(shown.locator("code")).toHaveText(/^vrn_/)
  await shown.getByRole("button", { name: "I have copied it" }).click()
  await expect(shown).toBeHidden()
  const row = page.getByRole("listitem").filter({ hasText: "ci" })
  await expect(row).toContainText("read only")
  await row.getByRole("button", { name: "Revoke" }).click()
  await expect(page.getByText("Token revoked. It stops working now.")).toBeVisible()
  await expect(row).toContainText("revoked")

  // the workspace spending limit is saved and can be removed
  await page.goto("/workspace")
  await page
    .getByRole("navigation", { name: "Workspace sections" })
    .getByRole("button", { name: "Spending limit" })
    .click()
  await page.getByLabel("Monthly limit in dollars").fill("5.5")
  await page.getByRole("button", { name: "Save limit" }).click()
  await expect(page.getByRole("button", { name: "Remove limit" })).toBeVisible()
  await page.getByRole("button", { name: "Remove limit" }).click()
  await expect(page.getByRole("button", { name: "Remove limit" })).toBeHidden()

  // an ingest token for real traffic is shown once and can be revoked
  await page.goto(`${project}/traffic`)
  await page.getByRole("tab", { name: "Connect an app" }).click()
  await page.locator("#token-name").fill("my-app")
  await page
    .locator("form")
    .filter({ has: page.locator("#token-name") })
    .getByRole("button")
    .click()
  await expect(page.getByRole("status").filter({ hasText: /once/i })).toBeVisible()
  await expect(page.getByText("my-app").first()).toBeVisible()
})
