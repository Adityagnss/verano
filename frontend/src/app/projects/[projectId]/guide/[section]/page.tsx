/** One section of the Prompting guide. */
import { GuideSectionPage } from "@/features/guide/components/guide-section-page"

export default async function Page({ params }: { params: Promise<{ projectId: string; section: string }> }) {
  const { projectId, section } = await params
  return <GuideSectionPage projectId={projectId} section={section} />
}
