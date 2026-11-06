/** Invite link page. */
import { InvitePage } from "@/features/teams/components/invite-page"

export default async function Page({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params
  return <InvitePage token={token} />
}
