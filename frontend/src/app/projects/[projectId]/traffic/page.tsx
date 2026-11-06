/** Real traffic: import, receive, turn into cases, score a sample and alert. */
import { TrafficStep } from "@/features/traffic/components/traffic-step"

export default async function Page({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params
  return <TrafficStep projectId={projectId} />
}
