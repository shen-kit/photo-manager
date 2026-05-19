"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { EyeOff, Eye, GitMerge, LoaderCircle, RefreshCcw, Users, Workflow } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { AppShell } from "@/components/app-shell";
import { LoginScreen } from "@/components/login-screen";
import { useToast } from "@/components/toast-provider";
import { listPeople, triggerPeopleClustering, updatePerson } from "@/lib/api/people";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";

const DEFAULT_CLUSTER = {
  threshold: 0.4,
  top_k: 30,
  min_cluster_size: 2,
};

export function PeoplePage() {
  const { queryClient, isBootstrapping, setAccessReady, accessReady, currentUser } =
    useSessionBootstrap();
  const { pushToast } = useToast();
  const [includeHidden, setIncludeHidden] = useState(false);
  const [searchValue, setSearchValue] = useState("");
  const [clusterValues, setClusterValues] = useState(DEFAULT_CLUSTER);
  const [draftNames, setDraftNames] = useState<Record<string, string>>({});

  const peopleQuery = useQuery({
    queryKey: ["people", includeHidden, searchValue],
    queryFn: () => listPeople({ include_hidden: includeHidden, search: searchValue }),
    enabled: accessReady,
  });

  const clusterMutation = useMutation({
    mutationFn: () => triggerPeopleClustering(clusterValues),
    onSuccess: async (job) => {
      pushToast(`Cluster job queued: ${job.id.slice(0, 8)}`, "success");
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error: Error) => pushToast(error.message, "error"),
  });

  const updatePersonMutation = useMutation({
    mutationFn: ({ personId, payload }: { personId: string; payload: { name?: string | null; is_hidden?: boolean } }) =>
      updatePerson(personId, payload),
    onSuccess: async (_, variables) => {
      pushToast("Person updated", "success");
      setDraftNames((current) => ({ ...current, [variables.personId]: "" }));
      await queryClient.invalidateQueries({ queryKey: ["people"] });
      await queryClient.invalidateQueries({ queryKey: ["search"] });
    },
    onError: (error: Error) => pushToast(error.message, "error"),
  });

  if (isBootstrapping) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-4 text-sm text-slate-300">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Preparing people view...
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
        }}
      />
    );
  }

  const people = peopleQuery.data ?? [];

  return (
    <AppShell
      currentUser={currentUser}
      title="People"
      description="Test clustering, review clustered people, and apply basic manual corrections."
      headerActions={
        <button
          type="button"
          onClick={() => clusterMutation.mutate()}
          disabled={clusterMutation.isPending}
          className="flex items-center gap-2 rounded-2xl border border-cyan-400/30 bg-cyan-400/10 px-4 py-3 text-sm text-cyan-200 transition hover:bg-cyan-400/20 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {clusterMutation.isPending ? (
            <LoaderCircle className="h-4 w-4 animate-spin" />
          ) : (
            <Workflow className="h-4 w-4" />
          )}
          Cluster faces
        </button>
      }
    >
      <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="space-y-6">
          <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
            <div className="mb-4 flex items-center gap-3">
              <div className="rounded-2xl border border-cyan-400/20 bg-cyan-400/10 p-2 text-cyan-300">
                <GitMerge className="h-4 w-4" />
              </div>
              <div>
                <h2 className="text-sm font-semibold text-white">Clustering</h2>
                <p className="text-xs text-slate-400">Queue a background clustering pass for unconfirmed faces.</p>
              </div>
            </div>
            <div className="space-y-3 text-sm text-slate-200">
              <label className="block">
                <span className="mb-1 block text-xs text-slate-400">Threshold</span>
                <input
                  type="number"
                  min={0.2}
                  max={0.8}
                  step={0.05}
                  value={clusterValues.threshold}
                  onChange={(event) =>
                    setClusterValues((current) => ({ ...current, threshold: Number(event.target.value) }))
                  }
                  className="w-full rounded-2xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400/50"
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-xs text-slate-400">Top K</span>
                <input
                  type="number"
                  min={5}
                  max={100}
                  step={1}
                  value={clusterValues.top_k}
                  onChange={(event) =>
                    setClusterValues((current) => ({ ...current, top_k: Number(event.target.value) }))
                  }
                  className="w-full rounded-2xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400/50"
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-xs text-slate-400">Min cluster size</span>
                <input
                  type="number"
                  min={2}
                  max={20}
                  step={1}
                  value={clusterValues.min_cluster_size}
                  onChange={(event) =>
                    setClusterValues((current) => ({ ...current, min_cluster_size: Number(event.target.value) }))
                  }
                  className="w-full rounded-2xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400/50"
                />
              </label>
              {clusterMutation.data ? (
                <Link href={`/jobs/${clusterMutation.data.id}`} className="block text-xs text-cyan-300 underline">
                  Job {clusterMutation.data.id}
                </Link>
              ) : null}
              {clusterMutation.isError ? (
                <p className="text-xs text-rose-300">{clusterMutation.error.message}</p>
              ) : null}
            </div>
          </section>

          <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
            <div className="mb-4 flex items-center gap-3">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-2 text-slate-300">
                <Users className="h-4 w-4" />
              </div>
              <div>
                <h2 className="text-sm font-semibold text-white">Filters</h2>
                <p className="text-xs text-slate-400">The backend already sorts by photo count.</p>
              </div>
            </div>
            <div className="space-y-3">
              <input
                value={searchValue}
                onChange={(event) => setSearchValue(event.target.value)}
                placeholder="Search person name"
                className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white outline-none focus:border-cyan-400/50"
              />
              <label className="flex items-center gap-2 text-xs text-slate-300">
                <input
                  type="checkbox"
                  checked={includeHidden}
                  onChange={(event) => setIncludeHidden(event.target.checked)}
                  className="h-4 w-4 rounded border-white/10 bg-black/20 text-cyan-400 focus:ring-cyan-400/40"
                />
                Include hidden people
              </label>
              <button
                type="button"
                onClick={() => void peopleQuery.refetch()}
                className="flex w-full items-center justify-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white transition hover:bg-white/10"
              >
                <RefreshCcw className="h-4 w-4" />
                Refresh list
              </button>
            </div>
          </section>
        </aside>

        <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
          <div className="mb-4 flex items-center justify-between gap-3 border-b border-white/10 pb-4">
            <div>
              <h2 className="text-lg font-semibold text-white">People</h2>
              <p className="text-sm text-slate-400">Unnamed people come from clustering. Manual updates are authoritative.</p>
            </div>
            {peopleQuery.isFetching ? <LoaderCircle className="h-4 w-4 animate-spin text-slate-400" /> : null}
          </div>

          {peopleQuery.isLoading ? (
            <div className="flex min-h-[280px] items-center justify-center text-sm text-slate-400">
              <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
              Loading people...
            </div>
          ) : null}

          {peopleQuery.isError ? (
            <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
              {peopleQuery.error.message}
            </div>
          ) : null}

          {!peopleQuery.isLoading && !peopleQuery.isError && people.length === 0 ? (
            <div className="flex min-h-[280px] items-center justify-center rounded-3xl border border-dashed border-white/10 text-sm text-slate-500">
              No people found.
            </div>
          ) : null}

          {people.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {people.map((person) => {
                const draftName = draftNames[person.id] ?? person.name ?? "";
                return (
                  <article
                    key={person.id}
                    className="overflow-hidden rounded-3xl border border-white/10 bg-ink-800/70"
                  >
                    <Link href={`/people/${person.id}`} className="block">
                      <div className="relative aspect-[4/3] overflow-hidden bg-black/30">
                        {person.thumbnail_crop_url ? (
                          <img
                            src={person.thumbnail_crop_url}
                            alt={person.name ?? "Unnamed person"}
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          <div className="flex h-full items-center justify-center text-sm text-slate-500">
                            No thumbnail
                          </div>
                        )}
                      </div>
                    </Link>
                    <div className="space-y-3 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <Link href={`/people/${person.id}`} className="text-sm font-semibold text-white hover:text-cyan-200">
                            {person.name?.trim() || "Unnamed person"}
                          </Link>
                          <p className="mt-1 text-xs text-slate-400">
                            {person.asset_count} photos · {person.face_count} faces
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() =>
                            updatePersonMutation.mutate({
                              personId: person.id,
                              payload: { is_hidden: !person.is_hidden },
                            })
                          }
                          className="rounded-full border border-white/10 p-2 text-slate-300 transition hover:bg-white/10 hover:text-white"
                        >
                          {person.is_hidden ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
                        </button>
                      </div>

                      <div className="flex gap-2">
                        <input
                          value={draftName}
                          onChange={(event) =>
                            setDraftNames((current) => ({ ...current, [person.id]: event.target.value }))
                          }
                          placeholder="Rename person"
                          className="min-w-0 flex-1 rounded-2xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-white outline-none focus:border-cyan-400/50"
                        />
                        <button
                          type="button"
                          onClick={() =>
                            updatePersonMutation.mutate({
                              personId: person.id,
                              payload: { name: draftName.trim() || null },
                            })
                          }
                          disabled={updatePersonMutation.isPending}
                          className="rounded-2xl bg-white/10 px-3 py-2 text-sm text-white transition hover:bg-white/15 disabled:opacity-60"
                        >
                          Save
                        </button>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : null}
        </section>
      </div>
    </AppShell>
  );
}
