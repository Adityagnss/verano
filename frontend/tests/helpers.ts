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
  const link = page.locator('[data-slot="sidebar-inner"]').getByRole("link", { name }).first()
  // below 1024px the sidebar lives in a drawer that the menu button opens
  if (!(await link.isVisible())) await page.getByRole("button", { name: "Open menu" }).click()
  await link.click()
}

/**
 * Fills the "Add examples" wizard: ticks the file kinds, uploads input files and a golden CSV, matches the columns
 * and moves on to the test cases. The match step waits while a file is still being read, so the click retries.
 */
export async function addExamples(
  page: Page,
  tickets: string[],
  golden: string,
  expectedAnswers: string,
): Promise<void> {
  const next = page.getByRole("button", { name: "Next", exact: true })
  await page.getByRole("checkbox", { name: "Input files" }).click()
  await page.getByRole("checkbox", { name: "Golden set" }).click()
  await next.click()
  await page.getByTestId("upload-inputs").setInputFiles(
    tickets.map((text, i) => ({
      name: `case${i + 1}.txt`,
      mimeType: "text/plain",
      buffer: Buffer.from(text),
    })),
  )
  await expect(page.getByText(`case${tickets.length}.txt`, { exact: true })).toBeVisible()
  await page.getByTestId("upload-golden").setInputFiles({
    name: "golden.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(golden),
  })
  await next.click()
  await page.getByRole("button", { name: "Check entries" }).click()
  await page.getByRole("button", { name: /^Import \d+ answers/ }).click()
  await expect(page.getByText(expectedAnswers).first()).toBeVisible()
  await expect(async () => {
    await next.click()
    await expect(page.getByRole("button", { name: "Next: test cases" })).toBeVisible({ timeout: 1000 })
  }).toPass({ timeout: 20000 })
  await page.getByRole("button", { name: "Next: test cases" }).click()
}
