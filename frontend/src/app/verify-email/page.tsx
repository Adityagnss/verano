/** Email confirmation page (the link in the confirmation email). */
import { VerifyEmailPage } from "@/features/teams/components/verify-email-page"

export default async function Page({ searchParams }: { searchParams: Promise<{ token?: string }> }) {
  const { token } = await searchParams
  return <VerifyEmailPage token={token ?? ""} />
}
