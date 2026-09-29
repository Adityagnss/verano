/** Project dashboard. */
import { DashboardPage } from "@/features/dashboard/components/dashboard-page"

export default async function Page({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params
  return <DashboardPage projectId={projectId} />
}
