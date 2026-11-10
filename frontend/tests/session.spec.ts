/**
 * The session survives a reload in every browser engine over plain http://localhost.
 * The access token lives only in memory, so a reload can only stay signed in if the
 * browser stored and sent back the httpOnly, Secure, SameSite=Strict refresh cookie.
 * This is the check that WebKit (Safari) accepts that cookie without HTTPS.
 */
import { expect, test } from "@playwright/test"

import { openAccountMenu, signOut, signUp, uniqueEmail } from "./helpers"

test("sign-up keeps you signed in across a reload, and sign-out ends the session", async ({ page }) => {
  const email = uniqueEmail("session")
  await signUp(page, email)

  await page.reload()
  await expect(page).toHaveURL(/\/projects$/)
  await openAccountMenu(page)
  await expect(page.getByTestId("account-email")).toHaveText(email)
  await page.keyboard.press("Escape")

  await signOut(page)
  await expect(page).toHaveURL(/\/login$/)
  await page.goto("/projects")
  await expect(page).toHaveURL(/\/login\?next=%2Fprojects$/)
})
