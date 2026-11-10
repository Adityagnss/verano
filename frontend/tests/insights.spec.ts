/**
 * Trends, History, Prompting guide and Usage and spend: opens each one and checks the main parts,
 * including the guide's paged sections and that nothing scrolls sideways at 390px wide.
 * Needs the stack started with VERANO_MOCK_PROVIDER_ENABLED=true (`make e2e`).
 */
import { expect, test, type Page } from "@playwright/test"

import { goToPage, openAccountMenu, signUp, uniqueEmail } from "./helpers"

async function noSidewaysScroll(page: Page): Promise<void> {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
}

test("the insight pages open, the guide pages through, and a phone does not scroll sideways", async ({
  page,
}) => {
  await signUp(page, uniqueEmail("insights"))
  await page.getByLabel("Project name").fill("Insights")
  await page.getByRole("button", { name: "Create project" }).click()
  await expect(page).toHaveURL(/\/projects\/[^/]+\//)
  const project = new URL(page.url()).pathname.split("/").slice(0, 3).join("/")

  await goToPage(page, /^Trends/)
  await expect(page.getByRole("heading", { name: "Trends", level: 1 })).toBeVisible()
  await expect(page.getByText("Nothing to show yet")).toBeVisible()

  await goToPage(page, /^History/)
  await expect(page.getByRole("heading", { name: "History", level: 1 })).toBeVisible()

  await goToPage(page, /^Prompting guide/)
  await expect(page.getByRole("heading", { name: "Prompting guide", level: 1 })).toBeVisible()
  await expect(page.getByRole("link", { name: /Cheat sheet/ })).toBeVisible()
  await page.getByRole("link", { name: /Cheat sheet/ }).click()
  await expect(page).toHaveURL(/\/guide\/cheat-sheet$/)
  await expect(page.getByRole("heading", { name: "Cheat sheet", level: 1 })).toBeVisible()
  await page.getByRole("link", { name: /^Next:/ }).click()
  await expect(page).toHaveURL(/\/guide\/techniques$/)
  await page.getByRole("link", { name: /^Previous:/ }).click()
  await expect(page).toHaveURL(/\/guide\/cheat-sheet$/)

  await page.goto(`${project}/guide/templates`)
  await expect(page.getByRole("button", { name: /Copy/ }).first()).toBeVisible()

  await page.setViewportSize({ width: 390, height: 800 })
  for (const path of ["guide", "guide/start-here", "guide/templates", "dashboard", "logbook"]) {
    await page.goto(`${project}/${path}`)
    await page.waitForLoadState("networkidle")
    await noSidewaysScroll(page)
  }
  await page.setViewportSize({ width: 1280, height: 800 })

  await page.goto(`${project}/guide`)
  await openAccountMenu(page)
  await page.getByRole("menuitem", { name: "Usage and spend" }).click()
  await expect(page.getByRole("heading", { name: "Usage and spend", level: 1 })).toBeVisible()
  await page.setViewportSize({ width: 390, height: 800 })
  await noSidewaysScroll(page)
})
