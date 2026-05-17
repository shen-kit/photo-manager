"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, LoaderCircle } from "lucide-react";
import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { JobStatusBadge } from "@/components/job-status-badge";
import { LoginScreen } from "@/components/login-screen";
import { getJob } from "@/lib/api/jobs";
import { formatDateTime, formatJson } from "@/lib/format";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";

type JobDetailPageProps = {
  jobId: string;
};

function DetailRow({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/20 px-4 py-3">
      <dt className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
        {label}
      </dt>
      <dd className="mt-2 text-sm text-slate-200">{value}</dd>
    </div>
  );
}

export function JobDetailPage({ jobId }: JobDetailPageProps) {
  const { queryClient, isBootstrapping, setAccessReady, accessReady, currentUser } =
    useSessionBootstrap();

  const jobQuery = useQuery({
    queryKey: ["jobs", jobId],
    queryFn: () => getJob(jobId),
    enabled: accessReady,
  });

  if (isBootstrapping) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-4 text-sm text-slate-300">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Preparing job detail...
        </div>
      </main>
    );
  }

  if (!accessReady || !currentUser) {
    return (
      <LoginScreen
        onLoggedIn={async () => {
          setAccessReady(true);
          await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
          await queryClient.invalidateQueries({ queryKey: ["jobs", jobId] });
        }}
      />
    );
  }

  const job = jobQuery.data;

  return (
    <AppShell
      currentUser={currentUser}
      title="Job Detail"
      description="Inspect the full lifecycle and payload of a background job."
    >
      <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
        <div className="mb-5 flex flex-col gap-4 border-b border-white/10 pb-4">
          <Link
            href="/jobs"
            className="inline-flex items-center gap-2 text-sm text-cyan-300 transition hover:text-cyan-200"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to jobs
          </Link>
          {job ? (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-3">
                <JobStatusBadge status={job.status} />
                <span className="text-xs uppercase tracking-[0.18em] text-slate-400">
                  {job.type}
                </span>
              </div>
              <h2 className="text-lg font-semibold text-white">{job.id}</h2>
              {job.progress_message ? (
                <p className="text-sm text-slate-300">{job.progress_message}</p>
              ) : null}
            </div>
          ) : null}
        </div>

        {jobQuery.isLoading ? (
          <div className="flex min-h-[280px] items-center justify-center text-sm text-slate-400">
            <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
            Loading job details...
          </div>
        ) : null}

        {jobQuery.isError ? (
          <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
            {(jobQuery.error as Error).message}
          </div>
        ) : null}

        {!jobQuery.isLoading && !jobQuery.isError && !job ? (
          <div className="flex min-h-[280px] flex-col items-center justify-center gap-3 rounded-3xl border border-dashed border-white/10 text-sm text-slate-500">
            <AlertTriangle className="h-5 w-5 text-slate-600" />
            Job not found.
          </div>
        ) : null}

        {job ? (
          <div className="space-y-5">
            <dl className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              <DetailRow label="Type" value={job.type} />
              <DetailRow label="Status" value={job.status} />
              <DetailRow
                label="Progress"
                value={`${job.progress_current}${job.progress_total != null ? ` / ${job.progress_total}` : ""}`}
              />
              <DetailRow
                label="Created"
                value={formatDateTime(job.created_at)}
              />
              <DetailRow
                label="Started"
                value={formatDateTime(job.started_at)}
              />
              <DetailRow
                label="Finished"
                value={formatDateTime(job.finished_at)}
              />
              <DetailRow
                label="Progress Message"
                value={job.progress_message ?? "—"}
              />
              <DetailRow
                label="Error Message"
                value={job.error_message ?? "—"}
              />
              <DetailRow label="ID" value={job.id} />
            </dl>

            <div className="grid gap-5 xl:grid-cols-2">
              <section className="rounded-3xl border border-white/10 bg-black/20 p-4">
                <h3 className="text-sm font-semibold text-white">Parameters</h3>
                <pre className="mt-3 text-xs leading-6 text-slate-200">
                  {formatJson(job.parameters)}
                </pre>
              </section>
              <section className="rounded-3xl border border-white/10 bg-black/20 p-4">
                <h3 className="text-sm font-semibold text-white">Result</h3>
                <pre className="mt-3 text-xs leading-6 text-slate-200">
                  {formatJson(job.result)}
                </pre>
              </section>
            </div>
          </div>
        ) : null}
      </section>
    </AppShell>
  );
}
