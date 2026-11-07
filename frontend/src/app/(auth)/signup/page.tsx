/** Sign-up page. */
import { Suspense } from "react"

import { SignUpForm } from "@/features/auth/components/sign-up-form"

export default function SignupPage() {
  return (
    <Suspense>
      <SignUpForm />
    </Suspense>
  )
}
