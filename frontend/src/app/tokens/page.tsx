/** API tokens page: make, scope and revoke the tokens used by the command line, CI and apps. */
import { RequireSession } from "@/components/common/require-session"
import { TokensPage } from "@/features/tokens/components/tokens-page"

export default function Page() {
  return (
    <RequireSession>
      <TokensPage />
    </RequireSession>
  )
}
