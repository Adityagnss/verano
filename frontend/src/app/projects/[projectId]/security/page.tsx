/** Security: attack pack, report and hardening. */
import { SecurityStep } from "@/features/security/components/security-step"

export default async function Page({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params
  return <SecurityStep projectId={projectId} />
}
