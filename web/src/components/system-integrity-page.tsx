"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle, RefreshCcw, ShieldCheck, Wrench } from "lucide-react";
import { useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { LoginScreen } from "@/components/login-screen";
import { useToast } from "@/components/toast-provider";
import {
  getDiagnosticRun,
  listDiagnosticRunItems,
  listDiagnosticRuns,
  listDiagnostics,
  repairDiagnosticRun,
  runDiagnostic,
} from "@/lib/api/system-integrity";
import { formatDateTime } from "@/lib/format";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import type { DiagnosticRun } from "@/lib/types";

function statusClass(status: string) {
  if (status === "completed") return "border-emerald-400/30 bg-emerald-400/10 text-emerald-200";
  if (status === "failed") return "border-rose-400/30 bg-rose-400/10 text-rose-200";
  if (status === "running" || status === "queued") return "border-cyan-400/30 bg-cyan-400/10 text-cyan-200";
  return "border-white/10 bg-white/5 text-slate-200";
}

function healthClass(health: string | null) {
  if (health === "healthy") return "text-emerald-300";
  if (health === "unhealthy") return "text-rose-300";
  if (health === "warning") return "text-amber-300";
  return "text-slate-400";
}

function runLabel(run: DiagnosticRun) {
  return `${run.diagnostic_key} · ${run.status} · ${formatDateTime(run.created_at)}`;
}

export function SystemIntegrityPage() {
  const { queryClient, isBootstrapping, setAccessReady, accessReady, currentUser } = useSessionBootstrap();
  const { pushToast } = useToast();
  const [selectedDiagnosticKey, setSelectedDiagnosticKey] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [itemsOffset, setItemsOffset] = useState(0);

  const diagnosticsQuery = useQuery({ queryKey: ["system-integrity", "diagnostics"], queryFn: listDiagnostics, enabled: accessReady });
  const runsQuery = useQuery({
    queryKey: ["system-integrity", "runs", selectedDiagnosticKey],
    queryFn: () => listDiagnosticRuns(selectedDiagnosticKey),
    enabled: accessReady,
    refetchInterval: 3000,
  });
  const runDetailQuery = useQuery({
    queryKey: ["system-integrity", "run", selectedRunId],
    queryFn: () => getDiagnosticRun(selectedRunId as string),
    enabled: accessReady && Boolean(selectedRunId),
    refetchInterval: 3000,
  });
  const itemsQuery = useQuery({
    queryKey: ["system-integrity", "items", selectedRunId, itemsOffset],
    queryFn: () => listDiagnosticRunItems(selectedRunId as string, itemsOffset, 100),
    enabled: accessReady && Boolean(selectedRunId),
  });

  const diagnostics = diagnosticsQuery.data?.items ?? [];
  const runs = runsQuery.data?.items ?? [];
  const selectedRun = runDetailQuery.data ?? runs.find((run) => run.id === selectedRunId) ?? null;
  const selectedDefinition = diagnostics.find((definition) => definition.key === selectedDiagnosticKey) ?? null;
  const items = itemsQuery.data?.items ?? [];
  const itemPage = itemsQuery.data;
  const latestRunsByKey = useMemo(() => new Map(runs.map((run) => [run.diagnostic_key, run])), [runs]);

  const runMutation = useMutation({
    mutationFn: runDiagnostic,
    onSuccess: async (response) => {
      pushToast(`Diagnostic queued: ${response.run.id.slice(0, 8)}`, "success");
      setSelectedRunId(response.run.id);
      await queryClient.invalidateQueries({ queryKey: ["system-integrity"] });
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error: Error) => pushToast(error.message, "error"),
  });

  const repairMutation = useMutation({
    mutationFn: repairDiagnosticRun,
    onSuccess: async (response) => {
      pushToast(`Repair queued: ${response.run.id.slice(0, 8)}`, "success");
      await queryClient.invalidateQueries({ queryKey: ["system-integrity"] });
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error: Error) => pushToast(error.message, "error"),
  });

  const refresh = async () => {
    await Promise.all([diagnosticsQuery.refetch(), runsQuery.refetch(), runDetailQuery.refetch(), itemsQuery.refetch()]);
  };

  if (isBootstrapping) {
    return <main className="flex min-h-screen items-center justify-center text-slate-300">Preparing integrity view...</main>;
  }

  if (!accessReady || !currentUser) {
    return <LoginScreen onLoggedIn={async () => { setAccessReady(true); await queryClient.invalidateQueries({ queryKey: ["auth", "me"] }); }} />;
  }

  return (
    <AppShell
      currentUser={currentUser}
      title="System Integrity"
      description="Development UI for persisted diagnostics, snapshot findings, and repair jobs."
      headerActions={<button type="button" onClick={() => void refresh()} className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white"><RefreshCcw className="h-4 w-4" /> Refresh</button>}
    >
      <div className="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
        <aside className="space-y-6">
          <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
            <div className="mb-4 flex items-center gap-3">
              <div className="rounded-2xl border border-cyan-400/20 bg-cyan-400/10 p-2 text-cyan-300"><ShieldCheck className="h-4 w-4" /></div>
              <div><h2 className="text-sm font-semibold text-white">Diagnostics</h2><p className="text-xs text-slate-400">Run deep checks on demand.</p></div>
            </div>
            {diagnosticsQuery.isLoading ? <p className="text-sm text-slate-400"><LoaderCircle className="mr-2 inline h-4 w-4 animate-spin" />Loading diagnostics...</p> : null}
            {diagnosticsQuery.isError ? <p className="text-sm text-rose-300">{diagnosticsQuery.error.message}</p> : null}
            <div className="space-y-3">
              {diagnostics.map((definition) => {
                const latest = latestRunsByKey.get(definition.key);
                const active = definition.active_run_id || latest?.status === "queued" || latest?.status === "running";
                return (
                  <article key={definition.key} className={`rounded-2xl border p-3 ${selectedDiagnosticKey === definition.key ? "border-cyan-400/40 bg-cyan-400/10" : "border-white/10 bg-white/5"}`}>
                    <button type="button" onClick={() => { setSelectedDiagnosticKey(definition.key); setSelectedRunId(latest?.id ?? definition.latest_run_id ?? null); setItemsOffset(0); }} className="w-full text-left">
                      <h3 className="text-sm font-semibold text-white">{definition.title}</h3>
                      <p className="mt-1 text-xs text-slate-400">{definition.key}</p>
                      <p className={`mt-2 text-xs ${healthClass(definition.latest_health_state ?? latest?.health_state ?? null)}`}>Latest: {definition.latest_status ?? latest?.status ?? "none"} · {definition.latest_health_state ?? latest?.health_state ?? "unknown"}</p>
                    </button>
                    <button type="button" onClick={() => { setSelectedDiagnosticKey(definition.key); runMutation.mutate(definition.key); }} disabled={runMutation.isPending || Boolean(active)} className="mt-3 flex w-full items-center justify-center gap-2 rounded-2xl border border-cyan-400/30 bg-cyan-400/10 px-3 py-2 text-sm text-cyan-200 disabled:opacity-60">
                      {runMutation.isPending && runMutation.variables === definition.key ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />} Run diagnostic
                    </button>
                    {definition.supports_repair ? <p className="mt-2 text-[11px] text-emerald-300">Repair: {definition.repair_job_key}</p> : <p className="mt-2 text-[11px] text-slate-500">Detect-only</p>}
                  </article>
                );
              })}
            </div>
          </section>
        </aside>

        <section className="space-y-6">
          <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
            <div className="mb-5 border-b border-white/10 pb-4">
              <h2 className="text-lg font-semibold text-white">Runs {selectedDefinition ? `for ${selectedDefinition.key}` : ""}</h2>
              <p className="text-sm text-slate-400">Retention keeps latest backend snapshots.</p>
            </div>
            {runsQuery.isLoading ? <p className="text-sm text-slate-400"><LoaderCircle className="mr-2 inline h-4 w-4 animate-spin" />Loading runs...</p> : null}
            {runsQuery.isError ? <p className="text-sm text-rose-300">{runsQuery.error.message}</p> : null}
            <div className="space-y-2">
              {runs.map((run) => (
                <button key={run.id} type="button" onClick={() => { setSelectedRunId(run.id); setItemsOffset(0); }} className={`w-full rounded-2xl border p-3 text-left ${selectedRunId === run.id ? "border-cyan-400/40 bg-cyan-400/10" : "border-white/10 bg-white/5"}`}>
                  <div className="flex flex-wrap items-center gap-2"><span className="text-sm font-semibold text-white">{runLabel(run)}</span><span className={`rounded-full border px-2 py-1 text-[11px] ${statusClass(run.status)}`}>{run.status}</span><span className={`text-xs ${healthClass(run.health_state)}`}>{run.health_state ?? "unknown"}</span></div>
                  <p className="mt-1 break-all text-xs text-slate-500">{run.id}</p>
                  {run.error_message ? <p className="mt-1 text-xs text-rose-300">{run.error_message}</p> : null}
                </button>
              ))}
            </div>
          </section>

          <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
            <div className="mb-5 flex flex-col gap-3 border-b border-white/10 pb-4 md:flex-row md:items-center md:justify-between">
              <div><h2 className="text-lg font-semibold text-white">Run detail</h2><p className="text-sm text-slate-400">Snapshot summary, jobs, findings.</p></div>
              <button type="button" onClick={() => selectedRunId && repairMutation.mutate(selectedRunId)} disabled={!selectedRun || selectedRun.status !== "completed" || !selectedRun.repair_job_key || repairMutation.isPending} className="flex items-center gap-2 rounded-2xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-200 disabled:opacity-60">
                {repairMutation.isPending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Wrench className="h-4 w-4" />} Repair from snapshot
              </button>
            </div>
            {!selectedRun ? <p className="text-sm text-slate-400">Select or run a diagnostic.</p> : null}
            {runDetailQuery.isError ? <p className="text-sm text-rose-300">{runDetailQuery.error.message}</p> : null}
            {selectedRun ? (
              <div className="space-y-4">
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-2xl border border-white/10 bg-black/20 p-3 text-xs text-slate-300"><p className="text-slate-500">Related job</p>{selectedRun.related_job_id ? <a href={`/jobs/${selectedRun.related_job_id}`} className="break-all text-cyan-300 underline">{selectedRun.related_job_id}</a> : "none"}</div>
                  <div className="rounded-2xl border border-white/10 bg-black/20 p-3 text-xs text-slate-300"><p className="text-slate-500">Repair job</p>{selectedRun.latest_repair_job_id ? <a href={`/jobs/${selectedRun.latest_repair_job_id}`} className="break-all text-cyan-300 underline">{selectedRun.latest_repair_job_id}</a> : "none"}</div>
                </div>
                <pre className="overflow-x-auto rounded-2xl border border-white/10 bg-black/20 p-4 text-xs leading-6 text-slate-200">{JSON.stringify({ summary: selectedRun.summary_json, sample_items: selectedRun.sample_items_json }, null, 2)}</pre>
                <div>
                  <div className="mb-3 flex items-center justify-between"><h3 className="text-sm font-semibold text-white">Findings</h3><p className="text-xs text-slate-400">{itemPage?.total ?? 0} total</p></div>
                  {itemsQuery.isLoading ? <p className="text-sm text-slate-400"><LoaderCircle className="mr-2 inline h-4 w-4 animate-spin" />Loading findings...</p> : null}
                  {itemsQuery.isError ? <p className="text-sm text-rose-300">{itemsQuery.error.message}</p> : null}
                  <div className="space-y-2">
                    {items.map((item) => (
                      <article key={item.id} className="rounded-2xl border border-white/10 bg-black/20 p-3 text-xs text-slate-300">
                        <div className="flex flex-wrap gap-2"><span className="rounded-full border border-white/10 px-2 py-1 text-white">{item.item_type}</span><span className="rounded-full border border-white/10 px-2 py-1">{item.reason_code}</span>{item.repairable ? <span className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-1 text-emerald-200">repairable</span> : null}</div>
                        <p className="mt-2 break-all">asset={item.asset_id ?? "-"} person={item.person_id ?? "-"} path={item.relative_path ?? "-"}</p>
                        {item.detail_json ? <pre className="mt-2 overflow-x-auto text-[11px] text-slate-400">{JSON.stringify(item.detail_json, null, 2)}</pre> : null}
                      </article>
                    ))}
                  </div>
                  <div className="mt-4 flex justify-between">
                    <button type="button" onClick={() => setItemsOffset(Math.max(0, itemsOffset - 100))} disabled={itemsOffset === 0} className="rounded-2xl border border-white/10 px-4 py-2 text-sm text-white disabled:opacity-60">Prev</button>
                    <button type="button" onClick={() => setItemsOffset(itemsOffset + 100)} disabled={!itemPage || itemsOffset + itemPage.limit >= itemPage.total} className="rounded-2xl border border-white/10 px-4 py-2 text-sm text-white disabled:opacity-60">Next</button>
                  </div>
                </div>
              </div>
            ) : null}
          </section>
        </section>
      </div>
    </AppShell>
  );
}
