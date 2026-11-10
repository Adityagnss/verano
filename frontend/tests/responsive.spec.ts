/**
 * Responsive audit. For each width (1440, 1280, 1024, 768, 390) it opens every page and checks:
 *   (a) the document never scrolls sideways,
 *   (b) the header's interactive elements do not overlap each other,
 *   (c) at 390px the navigation is reachable through a menu button,
 *   (d) at 390px every button and link in the header and navigation is at least 40px tall.
 * Needs the stack started with VERANO_MOCK_PROVIDER_ENABLED=true (`make e2e`). Set SCREENSHOT_DIR
 * to keep a picture of the shell at each width. Feature work adds its new routes to the arrays below.
 */
import { expect, test, type Page } from "@playwright/test"

import { signUp, uniqueEmail } from "./helpers"

/** Project pages, by route segment. Add new ones here. */
const PROJECT_ROUTES = [
  "keys",
  "prompt",
  "data",
  "tests",
  "run",
  "results",
  "improve",
  "apps",
  "review",
  "traffic",
  "security",
  "logbook",
  "dashboard",
  "guide",
  "guide/start-here",
  "guide/templates",
]
/** Pages outside a project. Add new ones here. */
const ACCOUNT_ROUTES = ["/projects", "/workspace", "/tokens", "/activity"]
const WIDTHS = [1440, 1280, 1024, 768, 390]
const MIN_TAP = 40

type Box = { name: string; x: number; y: number; width: number; height: number }

async function headerBoxes(page: Page): Promise<Box[]> {
  return page.evaluate(() => {
    const header = document.querySelector('[data-slot="app-header"]')
    if (!header) return []
    return Array.from(header.querySelectorAll<HTMLElement>("a[href], button, input, [role=button]"))
      .map((el) => {
        const r = el.getBoundingClientRect()
        const name = (el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 30)
        return { name, x: r.x, y: r.y, width: r.width, height: r.height }
      })
      .filter((box) => box.width > 0 && box.height > 0)
  })
}

function overlaps(a: Box, b: Box): boolean {
  const tolerance = 1
  return (
    a.x + a.width - tolerance > b.x &&
    b.x + b.width - tolerance > a.x &&
    a.y + a.height - tolerance > b.y &&
    b.y + b.height - tolerance > a.y
  )
}

async function auditPage(page: Page, label: string, width: number, report: string[]): Promise<void> {
  await expect(page.locator('[data-slot="app-header"]')).toBeVisible({ timeout: 30_000 })
  await expect(page.locator("main h1, main h2, main h3").first()).toBeVisible({ timeout: 30_000 })
  await page.waitForLoadState("networkidle")

  const scroll = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }))
  if (scroll.scrollWidth > scroll.clientWidth + 1)
    report.push(
      `${label} @${width}: page scrolls sideways (${scroll.scrollWidth}px wide in ${scroll.clientWidth}px)`,
    )

  const boxes = await headerBoxes(page)
  for (let i = 0; i < boxes.length; i++)
    for (let j = i + 1; j < boxes.length; j++)
      if (overlaps(boxes[i], boxes[j]))
        report.push(`${label} @${width}: header "${boxes[i].name}" overlaps "${boxes[j].name}"`)

  if (width === 390) {
    for (const box of boxes)
      if (box.height < MIN_TAP)
        report.push(`${label} @390: header "${box.name}" is ${Math.round(box.height)}px tall`)
  }
}

async function auditMenu(page: Page, label: string, report: string[]): Promise<void> {
  const menu = page.getByRole("button", { name: "Open menu" })
  if (!(await menu.isVisible())) {
    report.push(`${label} @390: no menu button`)
    return
  }
  await menu.click()
  const drawer = page.locator('[data-sidebar="sidebar"][data-mobile="true"]')
  await expect(drawer).toBeVisible()
  const links = await drawer.locator("a[href], button").evaluateAll((els) =>
    els
      .map((el) => ({
        name: (el.getAttribute("aria-label") || el.textContent || "").trim().slice(0, 30),
        height: el.getBoundingClientRect().height,
        width: el.getBoundingClientRect().width,
      }))
      .filter((item) => item.width > 0 && item.height > 0),
  )
  const shots = process.env.SCREENSHOT_DIR
  if (shots) await page.waitForTimeout(500)
  if (shots) await page.screenshot({ path: `${shots}/menu-390-${label}.png` })
  if (links.length < 5) report.push(`${label} @390: the menu has only ${links.length} entries`)
  for (const link of links)
    if (link.height < MIN_TAP)
      report.push(`${label} @390: menu "${link.name}" is ${Math.round(link.height)}px tall`)
  await page.keyboard.press("Escape")
  await expect(drawer).toBeHidden()
}

for (const width of WIDTHS) {
  test(`every page fits at ${width}px`, async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "layout is checked once, in Chromium")
    test.setTimeout(420_000)
    await page.setViewportSize({ width, height: width < 800 ? 800 : 900 })
    await signUp(page, uniqueEmail(`resp${width}`))
    await page.getByLabel("Project name").fill("Responsive check")
    await page.getByRole("button", { name: "Create project" }).click()
    await expect(page).toHaveURL(/\/projects\/[^/]+\//)
    const project = new URL(page.url()).pathname.split("/").slice(0, 3).join("/")

    const report: string[] = []
    const targets = [
      ...PROJECT_ROUTES.map((segment) => ({ label: segment, path: `${project}/${segment}` })),
      ...ACCOUNT_ROUTES.map((path) => ({ label: path, path })),
    ]
    for (const [index, target] of targets.entries()) {
      await page.goto(target.path)
      await auditPage(page, target.label, width, report)
      if (width === 390 && index % 6 === 0) await auditMenu(page, target.label, report)
      const dir = process.env.SCREENSHOT_DIR
      if (dir && (index === 0 || target.label === "/projects"))
        await page.screenshot({ path: `${dir}/shell-${width}-${target.label.replace(/\//g, "_")}.png` })
    }
    expect(report, `layout problems at ${width}px`).toEqual([])
  })
}
