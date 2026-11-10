/** Review answers: opens the page on a new project and checks the intro and the empty queue. Needs the stack (`make e2e`). */
import { expect, test } from "@playwright/test"

import { goToPage, signUp, uniqueEmail } from "./helpers"

test("Review answers explains itself and shows an empty queue", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "UI flow is engine-independent; covered once")
  await signUp(page, uniqueEmail("review"))
  await page.getByLabel("Project name").fill("Review check")
  await page.getByRole("button", { name: "Create project" }).click()
  await expect(page).toHaveURL(/\/projects\/[^/]+\//)
  await goToPage(page, /^Review answers/)
  await expect(page.getByRole("heading", { level: 1, name: "Review answers" })).toBeVisible()
  await expect(page.getByText("Nothing to check yet")).toBeVisible()
  await expect(page.getByText(/Why 30 answers/)).toBeVisible()
  await expect(page.getByTestId("agreement-meter")).toBeVisible()
})
