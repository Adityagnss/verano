import { expect, test } from "@playwright/test"

import { signUp, uniqueEmail } from "./helpers"

test("first visit offers three paths; Home shows the pipeline and the next step", async ({ page }) => {
  await signUp(page, uniqueEmail("entry"))
  await expect(page.getByRole("button", { name: /Compare models on a prompt/ })).toBeVisible()
  await expect(page.getByRole("button", { name: /Test an app I already run/ })).toBeVisible()

  // the command-line path shows the three commands
  await page.getByRole("button", { name: /Bring prompts from my code/ }).click()
  const dialog = page.getByRole("dialog")
  await expect(dialog.getByText("verano login")).toBeVisible()
  await expect(dialog.getByText("verano push")).toBeVisible()
  await dialog.getByRole("button", { name: "Open the project" }).click()

  // project Home: the pipeline, the next step and the side cards
  await expect(page).toHaveURL(/\/projects\/[^/]+$/)
  await expect(page.getByRole("list", { name: "Your progress" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Keys: Up next" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Connect a model provider" })).toBeVisible()
  await page
    .getByRole("link", { name: /Connect models/ })
    .first()
    .click()
  await expect(page).toHaveURL(/\/keys$/)
})

test("workspace tabs and API tokens page open with their intros", async ({ page }) => {
  await signUp(page, uniqueEmail("entry2"))
  await page.goto("/workspace")
  await expect(page.getByRole("heading", { name: "Workspace", level: 1 })).toBeVisible()
  await page.getByRole("tab", { name: "Spending limit" }).click()
  await page.goto("/tokens")
  await expect(page.getByRole("heading", { name: "API tokens", level: 1 })).toBeVisible()
})

test("sign-in page says what Verano is", async ({ page }) => {
  await page.goto("/login")
  await expect(page.getByText("What is Verano?")).toBeVisible()
})
