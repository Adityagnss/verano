/** Shared steps for the browser tests. */
import { expect, type Page } from "@playwright/test"

export const PASSWORD = "correct horse battery"

export function uniqueEmail(label: string): string {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`
}

export async function signUp(page: Page, email: string): Promise<void> {
  await page.goto("/signup")
  await page.getByLabel("Your name").fill("Ada")
  await page.getByLabel("Email").fill(email)
  await page.getByLabel("Password").fill(PASSWORD)
  await page.getByRole("button", { name: "Create account" }).click()
  await expect(page).toHaveURL(/\/projects$/)
  await expect(page.getByText(email)).toBeVisible()
}
