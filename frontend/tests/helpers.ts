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
  await expect(page.getByRole("button", { name: "Account menu" })).toBeVisible()
}

/** Opens the header's account menu (email, usage, workspace, tokens, sign out). */
export async function openAccountMenu(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Account menu" }).click()
}

/** Signs out through the account menu. */
export async function signOut(page: Page): Promise<void> {
  await openAccountMenu(page)
  await page.getByRole("menuitem", { name: "Sign out" }).click()
}

/** Chooses Light, Dark or "Same as your system" from the header's theme menu. */
export async function chooseTheme(
  page: Page,
  label: "Light" | "Dark" | "Same as your system",
): Promise<void> {
  await page.getByRole("button", { name: /^Color theme/ }).click()
  await page.getByRole("menuitemradio", { name: label }).click()
}

/** Clicks a page link in the sidebar by its (new) name, for example "Compare results". */
export async function goToPage(page: Page, name: string | RegExp): Promise<void> {
  await page.locator('[data-slot="sidebar-inner"]').getByRole("link", { name }).first().click()
}
