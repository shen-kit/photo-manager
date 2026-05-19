import { PersonDetailPage } from "@/components/person-detail-page";

export default async function PersonDetailRoutePage({
  params,
}: {
  params: Promise<{ personId: string }>;
}) {
  const { personId } = await params;
  return <PersonDetailPage personId={personId} />;
}
