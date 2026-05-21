"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, LoaderCircle, Play, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useToast } from "@/components/toast-provider";
import { ApiError } from "@/lib/api/client";
import { getAvailableJobs, runManualJob } from "@/lib/api/jobs";
import { formatDateTime } from "@/lib/format";
import type {
  Job,
  JobStatus,
  ManualJobDefinition,
  ManualJobParameter,
  ManualJobRunPayload,
} from "@/lib/types";

const ACTIVE_JOB_STATUSES = new Set<JobStatus>(["queued", "running"]);

type ManualJobsLauncherProps = {
  accessReady: boolean;
  jobs: Job[];
};

function getActiveJobForKey(jobKey: string, jobs: Job[]) {
  return jobs.find(
    (job) =>
      job.job_key === jobKey &&
      ACTIVE_JOB_STATUSES.has(job.status),
  );
}

function getConflictActiveJobId(error: ApiError) {
  const nestedDetail = error.payload?.detail;
  if (!nestedDetail || typeof nestedDetail !== "object") {
    return null;
  }

  const activeJobId = (nestedDetail as Record<string, unknown>).active_job_id;
  return typeof activeJobId === "string" ? activeJobId : null;
}

function getButtonLabel(status: JobStatus | null | undefined) {
  if (status === "queued") {
    return "Queued";
  }
  if (status === "running") {
    return "Running";
  }
  return "Run";
}

function formatPendingCount(count: number | null) {
  if (count == null) {
    return "Candidate count unavailable";
  }
  return `${count} candidate${count === 1 ? "" : "s"}`;
}

function buildInitialParams(item: ManualJobDefinition): Record<string, unknown> {
  const initial = { ...item.default_params };
  for (const parameter of item.parameters) {
    if (!(parameter.name in initial)) {
      initial[parameter.name] = parameter.default ?? null;
    }
  }
  return initial;
}

function formatParameterSummary(item: ManualJobDefinition) {
  if (item.parameters.length === 0) {
    return "No parameters";
  }
  return item.parameters.map((parameter) => parameter.name).join(", ");
}

function normalizeRunPayload(
  item: ManualJobDefinition,
  params: Record<string, unknown>,
): ManualJobRunPayload | undefined {
  if (item.parameters.length === 0) {
    return undefined;
  }
  const normalized: Record<string, unknown> = {};
  for (const parameter of item.parameters) {
    if (!(parameter.name in params)) {
      continue;
    }
    normalized[parameter.name] = params[parameter.name];
  }
  return { params: normalized };
}

function NumericParameterInput({
  parameter,
  value,
  disabled,
  onChange,
}: {
  parameter: ManualJobParameter;
  value: unknown;
  disabled: boolean;
  onChange: (value: number | null) => void;
}) {
  const step =
    parameter.step != null
      ? String(parameter.step)
      : parameter.type === "integer"
        ? "1"
        : "any";

  return (
    <input
      type="number"
      value={typeof value === "number" ? String(value) : ""}
      min={parameter.minimum ?? undefined}
      max={parameter.maximum ?? undefined}
      step={step}
      disabled={disabled}
      onChange={(event) => {
        const rawValue = event.target.value.trim();
        if (!rawValue) {
          onChange(null);
          return;
        }
        const parsedValue =
          parameter.type === "integer"
            ? Number.parseInt(rawValue, 10)
            : Number.parseFloat(rawValue);
        onChange(Number.isNaN(parsedValue) ? null : parsedValue);
      }}
      className="w-full rounded-2xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-white outline-none transition focus:border-cyan-400/50 disabled:cursor-not-allowed disabled:text-slate-500"
    />
  );
}

function ManualJobCard({
  item,
  activeJob,
  isRunning,
  params,
  onParamChange,
  onRun,
}: {
  item: ManualJobDefinition;
  activeJob: Job | undefined;
  isRunning: boolean;
  params: Record<string, unknown>;
  onParamChange: (jobKey: string, parameterName: string, value: unknown) => void;
  onRun: (jobKey: string, payload?: ManualJobRunPayload) => void;
}) {
  const activeStatus = activeJob?.status ?? item.active_status;
  const activeJobId = activeJob?.id ?? item.active_job_id;
  const isActive = activeStatus != null && ACTIVE_JOB_STATUSES.has(activeStatus);

  return (
    <article className="flex h-full flex-col rounded-3xl border border-white/10 bg-ink-800/50 p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-300">
              {item.category}
            </span>
            <span className="rounded-full border border-white/10 bg-black/20 px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-400">
              {item.mode}
            </span>
          </div>
          <h3 className="text-base font-semibold text-white">{item.title}</h3>
        </div>
        {isActive ? (
          <span className="rounded-full border border-cyan-400/30 bg-cyan-500/10 px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-cyan-200">
            {activeStatus}
          </span>
        ) : null}
      </div>

      <p className="mt-3 text-sm leading-6 text-slate-300">{item.description}</p>

      <dl className="mt-4 grid gap-3 text-xs text-slate-400 sm:grid-cols-2">
        <div>
          <dt className="uppercase tracking-[0.18em] text-slate-500">Candidates</dt>
          <dd className="mt-1 text-slate-200">{formatPendingCount(item.pending_count)}</dd>
        </div>
        <div>
          <dt className="uppercase tracking-[0.18em] text-slate-500">Last Finished</dt>
          <dd className="mt-1 text-slate-200">{formatDateTime(item.last_finished_at)}</dd>
        </div>
      </dl>

      <div className="mt-4 min-h-10 text-sm text-slate-300">
        {isActive && activeJobId ? (
          <Link
            href={`/jobs/${activeJobId}`}
            className="text-cyan-300 transition hover:text-cyan-200"
          >
            View active job {activeJobId.slice(0, 8)}
          </Link>
        ) : item.last_job_id ? (
          <Link
            href={`/jobs/${item.last_job_id}`}
            className="text-slate-400 transition hover:text-slate-200"
          >
            View last job {item.last_job_id.slice(0, 8)}
          </Link>
        ) : (
          <span className="text-slate-500">No runs yet</span>
        )}
      </div>

      {item.parameters.length > 0 ? (
        <div className="mt-4 space-y-3 rounded-2xl border border-white/10 bg-black/20 p-4">
          {item.parameters.map((parameter) => {
            const value = params[parameter.name];
            return (
              <label key={parameter.name} className="block space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium text-slate-200">
                    {parameter.name}
                  </span>
                  <span className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
                    {parameter.type}
                  </span>
                </div>
                {parameter.description ? (
                  <p className="text-xs leading-5 text-slate-400">
                    {parameter.description}
                  </p>
                ) : null}
                {parameter.type === "boolean" ? (
                  <span className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-200">
                    <input
                      type="checkbox"
                      checked={Boolean(value)}
                      disabled={isActive || isRunning}
                      onChange={(event) =>
                        onParamChange(
                          item.job_key,
                          parameter.name,
                          event.target.checked,
                        )
                      }
                      className="h-4 w-4 rounded border-white/10 bg-black/20 text-cyan-400 focus:ring-cyan-400/40"
                    />
                    <span>{Boolean(value) ? "Enabled" : "Disabled"}</span>
                  </span>
                ) : (
                  <NumericParameterInput
                    parameter={parameter}
                    value={value}
                    disabled={isActive || isRunning}
                    onChange={(nextValue) =>
                      onParamChange(item.job_key, parameter.name, nextValue)
                    }
                  />
                )}
              </label>
            );
          })}
        </div>
      ) : null}

      <div className="mt-5 flex items-center justify-between gap-3">
        <div className="text-xs text-slate-500">
          {formatParameterSummary(item)}
        </div>
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-full border border-cyan-400/30 bg-cyan-500/10 px-4 py-2 text-sm font-medium text-cyan-100 transition hover:bg-cyan-500/20 disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-white/5 disabled:text-slate-500"
          disabled={isActive || isRunning}
          onClick={() => onRun(item.job_key, normalizeRunPayload(item, params))}
        >
          {isRunning ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          {isRunning ? "Starting..." : getButtonLabel(activeStatus)}
        </button>
      </div>
    </article>
  );
}

export function ManualJobsLauncher({ accessReady, jobs }: ManualJobsLauncherProps) {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const [jobParams, setJobParams] = useState<Record<string, Record<string, unknown>>>(
    {},
  );

  const availableJobsQuery = useQuery({
    queryKey: ["jobs", "available"],
    queryFn: getAvailableJobs,
    enabled: accessReady,
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      return items.some((item) => item.active_status && ACTIVE_JOB_STATUSES.has(item.active_status))
        ? 3000
        : false;
    },
  });

  useEffect(() => {
    const items = availableJobsQuery.data?.items ?? [];
    if (items.length === 0) {
      return;
    }
    setJobParams((current) => {
      const next = { ...current };
      for (const item of items) {
        if (!(item.job_key in next)) {
          next[item.job_key] = buildInitialParams(item);
        }
      }
      return next;
    });
  }, [availableJobsQuery.data]);

  const runJobMutation = useMutation({
    mutationFn: ({
      jobKey,
      payload,
    }: {
      jobKey: string;
      payload?: ManualJobRunPayload;
    }) => runManualJob(jobKey, payload),
    onSuccess: async (response, variables) => {
      const item = availableJobsQuery.data?.items.find((job) => job.job_key === variables.jobKey);
      pushToast(
        `${item?.title ?? variables.jobKey} queued: ${response.job.id.slice(0, 8)}`,
        "success",
      );
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: async (error, variables) => {
      if (error instanceof ApiError && error.status === 409) {
        const activeJobId = getConflictActiveJobId(error);
        pushToast(
          activeJobId
            ? `Job is already running: ${activeJobId.slice(0, 8)}`
            : "Job is already running",
          "info",
        );
        await queryClient.invalidateQueries({ queryKey: ["jobs"] });
        return;
      }

      const message = error instanceof Error ? error.message : `Failed to run ${variables.jobKey}`;
      pushToast(message, "error");
    },
  });

  const items = availableJobsQuery.data?.items ?? [];

  const handleParamChange = (
    jobKey: string,
    parameterName: string,
    value: unknown,
  ) => {
    setJobParams((current) => ({
      ...current,
      [jobKey]: {
        ...(current[jobKey] ?? {}),
        [parameterName]: value,
      },
    }));
  };

  return (
    <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
      <div className="mb-5 flex flex-col gap-4 border-b border-white/10 pb-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Manual Jobs</h2>
          <p className="text-sm text-slate-400">
            Launch maintenance jobs without replacing the existing history and detail views.
          </p>
        </div>
        <button
          type="button"
          className="inline-flex items-center gap-2 self-start rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:text-slate-500"
          disabled={availableJobsQuery.isFetching}
          onClick={() => void availableJobsQuery.refetch()}
        >
          <RefreshCw
            className={`h-4 w-4 ${availableJobsQuery.isFetching ? "animate-spin" : ""}`}
          />
          Refresh
        </button>
      </div>

      {availableJobsQuery.isLoading ? (
        <div className="flex min-h-[220px] items-center justify-center text-sm text-slate-400">
          <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
          Loading available jobs...
        </div>
      ) : null}

      {availableJobsQuery.isError ? (
        <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {(availableJobsQuery.error as Error).message}
        </div>
      ) : null}

      {!availableJobsQuery.isLoading && !availableJobsQuery.isError && items.length === 0 ? (
        <div className="flex min-h-[220px] flex-col items-center justify-center gap-3 rounded-3xl border border-dashed border-white/10 text-sm text-slate-500">
          <AlertTriangle className="h-5 w-5 text-slate-600" />
          No manual jobs available.
        </div>
      ) : null}

      {items.length > 0 ? (
        <div className="grid gap-4 xl:grid-cols-2">
          {items.map((item) => {
            const activeJob = getActiveJobForKey(item.job_key, jobs);
            const isStarting =
              runJobMutation.isPending && runJobMutation.variables?.jobKey === item.job_key;

            return (
              <ManualJobCard
                key={item.job_key}
                item={item}
                activeJob={activeJob}
                isRunning={isStarting}
                params={jobParams[item.job_key] ?? buildInitialParams(item)}
                onParamChange={handleParamChange}
                onRun={(jobKey, payload) => runJobMutation.mutate({ jobKey, payload })}
              />
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
