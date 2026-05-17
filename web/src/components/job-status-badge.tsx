import type { JobStatus } from "@/lib/types";

const statusStyles: Record<JobStatus, string> = {
  queued: "border-slate-500/30 bg-slate-500/10 text-slate-200",
  running: "border-cyan-500/30 bg-cyan-500/10 text-cyan-200",
  completed: "border-emerald-500/30 bg-emerald-500/10 text-emerald-200",
  failed: "border-rose-500/30 bg-rose-500/10 text-rose-200",
  cancelled: "border-amber-500/30 bg-amber-500/10 text-amber-200",
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.18em] ${statusStyles[status]}`}
    >
      {status}
    </span>
  );
}
