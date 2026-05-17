import { JobDetailPage } from "@/components/job-detail-page";

export default async function JobDetailRoutePage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;
  return <JobDetailPage jobId={jobId} />;
}
