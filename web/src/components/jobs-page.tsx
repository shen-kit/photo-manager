"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, LoaderCircle } from "lucide-react";
import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { JobStatusBadge } from "@/components/job-status-badge";
import { LoginScreen } from "@/components/login-screen";
import { ManualJobsLauncher } from "@/components/manual-jobs-launcher";
import { getJobs } from "@/lib/api/jobs";
import { formatDateTime } from "@/lib/format";
import type { JobStatus } from "@/lib/types";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";

const ACTIVE_JOB_STATUSES = new Set<JobStatus>(["queued", "running"]);

function formatProgress(current: number, total: number | null) {
  if (total == null) {
    return `${current}`;
  }
  return `${current} / ${total}`;
}

export function JobsPage() {
  const { queryClient, isBootstrapping, setAccessReady, accessReady, currentUser } =
    useSessionBootstrap();

  const jobsQuery = useQuery({
    queryKey: ["jobs"],
    queryFn: getJobs,
    enabled: accessReady,
    refetchInterval: (query) => {
      const jobs = query.state.data ?? [];
      return jobs.some((job) => ACTIVE_JOB_STATUSES.has(job.status)) ? 3000 : false;
    },
  });

  if (isBootstrapping) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-4 text-sm text-slate-300">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Preparing jobs view...
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
          await queryClient.invalidateQueries({ queryKey: ["jobs"] });
        }}
      />
    );
  }

  const jobs = jobsQuery.data ?? [];

  return (
    <AppShell
      currentUser={currentUser}
      title="Jobs"
      description="Inspect queued, running, completed, and failed background work."
    >
      <ManualJobsLauncher accessReady={accessReady} jobs={jobs} />

      <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
        <div className="mb-5 flex items-end justify-between border-b border-white/10 pb-4">
          <div>
            <h2 className="text-lg font-semibold text-white">All Jobs</h2>
            <p className="text-sm text-slate-400">
              {jobs.length} background job{jobs.length === 1 ? "" : "s"}
            </p>
          </div>
          {jobsQuery.isFetching ? (
            <p className="text-xs text-cyan-300">Refreshing jobs...</p>
          ) : null}
        </div>

        {jobsQuery.isLoading ? (
          <div className="flex min-h-[280px] items-center justify-center text-sm text-slate-400">
            <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
            Loading jobs...
          </div>
        ) : null}

        {jobsQuery.isError ? (
          <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
            {(jobsQuery.error as Error).message}
          </div>
        ) : null}

        {!jobsQuery.isLoading && !jobsQuery.isError && jobs.length === 0 ? (
          <div className="flex min-h-[280px] flex-col items-center justify-center gap-3 rounded-3xl border border-dashed border-white/10 text-sm text-slate-500">
            <AlertTriangle className="h-5 w-5 text-slate-600" />
            No jobs found.
          </div>
        ) : null}

        {jobs.length > 0 ? (
          <div className="space-y-3">
            {jobs.map((job) => (
              <Link
                key={job.id}
                href={`/jobs/${job.id}`}
                className="block rounded-3xl border border-white/10 bg-ink-800/60 p-4 transition hover:border-white/20 hover:bg-ink-800"
              >
                <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-3">
                      <JobStatusBadge status={job.status} />
                      <span className="text-xs uppercase tracking-[0.18em] text-slate-400">
                        {job.type}
                      </span>
                    </div>
                    <p className="text-sm font-semibold text-white">{job.id}</p>
                    {job.progress_message ? (
                      <p className="text-sm text-slate-300">
                        {job.progress_message}
                      </p>
                    ) : null}
                    {job.error_message ? (
                      <p className="text-sm text-rose-300">{job.error_message}</p>
                    ) : null}
                  </div>

                  <dl className="grid gap-3 text-xs text-slate-400 sm:grid-cols-2 lg:grid-cols-4">
                    <div>
                      <dt className="uppercase tracking-[0.18em] text-slate-500">
                        Progress
                      </dt>
                      <dd className="mt-1 text-slate-200">
                        {formatProgress(job.progress_current, job.progress_total)}
                      </dd>
                    </div>
                    <div>
                      <dt className="uppercase tracking-[0.18em] text-slate-500">
                        Created
                      </dt>
                      <dd className="mt-1 text-slate-200">
                        {formatDateTime(job.created_at)}
                      </dd>
                    </div>
                    <div>
                      <dt className="uppercase tracking-[0.18em] text-slate-500">
                        Started
                      </dt>
                      <dd className="mt-1 text-slate-200">
                        {formatDateTime(job.started_at)}
                      </dd>
                    </div>
                    <div>
                      <dt className="uppercase tracking-[0.18em] text-slate-500">
                        Finished
                      </dt>
                      <dd className="mt-1 text-slate-200">
                        {formatDateTime(job.finished_at)}
                      </dd>
                    </div>
                  </dl>
                </div>
              </Link>
            ))}
          </div>
        ) : null}
      </section>
    </AppShell>
  );
}
