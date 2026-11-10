/**
 * Test your own app: the three-step connect flow. The server refuses addresses inside the network, so
 * this spec checks the guidance (address check, templates, live preview, Advanced) and that an
 * unreachable app is explained in plain words, rather than a successful call.
 */
import { expect, test } from "@playwright/test"

import { goToPage, signUp, uniqueEmail } from "./helpers"

test("connecting an app is guided in three steps", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "the flow is engine-independent; covered once")
  test.setTimeout(120_000)
  await signUp(page, uniqueEmail("apps"))
  await page.getByLabel("Project name").fill("Apps check")
  await page.getByRole("button", { name: "Create project" }).click()
  await expect(page).toHaveURL(/\/projects\/[^/]+\//)

  await goToPage(page, /^Test your own app/)
  await expect(page.getByRole("heading", { level: 1, name: "Test your own app" })).toBeVisible()
  await expect(page.getByText("No app connected yet.")).toBeVisible()

  await page.getByRole("button", { name: "Connect an app" }).first().click()
  // step 1 asks only for the address
  await expect(page.getByLabel("Address")).toBeVisible()
  await expect(page.getByLabel("Where is the answer?")).toHaveCount(0)
  await page.getByRole("button", { name: "Next" }).click()
  await expect(page.getByText(/Enter your app's address/)).toBeVisible()

  await page.getByLabel("Address").fill("http://127.0.0.1:9/ask")
  await page.getByRole("button", { name: "Check connection" }).click()
  await expect(page.getByText(/could not|refused|error/i).first()).toBeVisible({ timeout: 30_000 })

  // step 2: templates fill the details, a preview shows the request
  await page.getByRole("button", { name: "Next" }).click()
  await expect(page.getByRole("radio", { name: /RAG app that returns sources/ })).toBeVisible()
  await page.getByRole("radio", { name: /OpenAI-style chat/ }).click()
  await expect(page.getByLabel("The request Verano will send")).toContainText("messages")
  await page.getByRole("button", { name: /^Advanced/ }).click()
  await expect(page.getByLabel("Where is the answer?")).toHaveValue("$.choices[0].message.content")
  await expect(page.getByLabel("Sign-in")).toBeVisible()
})
