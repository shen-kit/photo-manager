"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, GitMerge, LoaderCircle, RefreshCcw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { AssetDetailModal } from "@/components/asset-detail-modal";
import { LoginScreen } from "@/components/login-screen";
import { useToast } from "@/components/toast-provider";
import { getPerson, getPersonAssets, listPeople, mergePeople, updatePerson, updatePersonThumbnail } from "@/lib/api/people";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import type { AssetListItem } from "@/lib/types";

const PAGE_SIZE = 24;

function formatDimension(asset: AssetListItem) {
  if (!asset.width || !asset.height) {
    return "Unknown size";
  }
  return `${asset.width} x ${asset.height}`;
}

export function PersonDetailPage({ personId }: { personId: string }) {
  const { queryClient, isBootstrapping, setAccessReady, accessReady, currentUser } =
    useSessionBootstrap();
  const { pushToast } = useToast();
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");
  const [mergeTargetId, setMergeTargetId] = useState("");

  const personQuery = useQuery({
    queryKey: ["person", personId],
    queryFn: () => getPerson(personId),
    enabled: accessReady,
  });

  const assetsQuery = useQuery({
    queryKey: ["person-assets", personId],
    queryFn: () => getPersonAssets(personId, 1, PAGE_SIZE),
    enabled: accessReady,
  });

  const peopleQuery = useQuery({
    queryKey: ["people", "merge-options"],
    queryFn: () => listPeople({ include_hidden: true }),
    enabled: accessReady,
  });

  const updatePersonMutation = useMutation({
    mutationFn: (payload: { name?: string | null; is_hidden?: boolean }) =>
      updatePerson(personId, payload),
    onSuccess: async (person) => {
      setDraftName(person.name ?? "");
      pushToast("Person updated", "success");
      await queryClient.invalidateQueries({ queryKey: ["person", personId] });
      await queryClient.invalidateQueries({ queryKey: ["people"] });
      await queryClient.invalidateQueries({ queryKey: ["search"] });
    },
    onError: (error: Error) => pushToast(error.message, "error"),
  });

  const mergeMutation = useMutation({
    mutationFn: () => mergePeople(personId, mergeTargetId),
    onSuccess: async (summary) => {
      pushToast(`Merged ${summary.faces_moved} faces`, "success");
      await queryClient.invalidateQueries({ queryKey: ["people"] });
      window.location.href = `/people/${summary.target_person_id}`;
    },
    onError: (error: Error) => pushToast(error.message, "error"),
  });

  const updateThumbnailMutation = useMutation({
    mutationFn: (assetId: string) => updatePersonThumbnail(personId, assetId),
    onSuccess: async () => {
      pushToast("Person thumbnail updated", "success");
      await queryClient.invalidateQueries({ queryKey: ["person", personId] });
      await queryClient.invalidateQueries({ queryKey: ["people"] });
    },
    onError: (error: Error) => pushToast(error.message, "error"),
  });

  const person = personQuery.data;
  const assets = assetsQuery.data?.items ?? [];
  const mergeOptions = useMemo(
    () => (peopleQuery.data ?? []).filter((candidate) => candidate.id !== personId),
    [peopleQuery.data, personId],
  );

  useEffect(() => {
    if (person) {
      setDraftName(person.name ?? "");
    }
  }, [person?.id, person?.name]);

  if (isBootstrapping) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-4 text-sm text-slate-300">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Preparing person view...
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

  return (
    <>
      <AppShell
        currentUser={currentUser}
        title={person?.name?.trim() || "Unnamed person"}
        description="Inspect clustered assets and apply basic person-level corrections."
        headerActions={
          <button
            type="button"
            onClick={() => {
              void personQuery.refetch();
              void assetsQuery.refetch();
            }}
            className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-slate-300 transition hover:bg-white/[0.07]"
          >
            <RefreshCcw className="h-4 w-4" />
            Refresh
          </button>
        }
      >
        <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
          <aside className="space-y-6">
            <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
              {personQuery.isLoading ? (
                <div className="text-sm text-slate-400">Loading person...</div>
              ) : null}
              {personQuery.isError ? (
                <div className="text-sm text-rose-300">{personQuery.error.message}</div>
              ) : null}
              {person ? (
                <div className="space-y-4">
                  <div className="overflow-hidden rounded-3xl border border-white/10 bg-black/20">
                    {person.thumbnail_url ? (
                      <img
                        src={person.thumbnail_url}
                        alt={person.name ?? "Unnamed person"}
                        className="aspect-square w-full object-cover"
                      />
                    ) : (
                      <div className="flex aspect-square items-center justify-center text-sm text-slate-500">
                        No person thumbnail
                      </div>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-xs text-slate-400">
                    <div className="rounded-2xl border border-white/10 bg-black/20 p-3">
                      <div className="text-lg font-semibold text-white">{person.asset_count}</div>
                      Photos
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-black/20 p-3">
                      <div className="text-lg font-semibold text-white">{person.face_count}</div>
                      Faces
                    </div>
                  </div>
                  <div className="space-y-3">
                    <input
                      value={draftName}
                      onChange={(event) => setDraftName(event.target.value)}
                      placeholder="Rename person"
                      className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white outline-none focus:border-cyan-400/50"
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => updatePersonMutation.mutate({ name: draftName.trim() || null })}
                        disabled={updatePersonMutation.isPending}
                        className="flex-1 rounded-2xl bg-white/10 px-4 py-3 text-sm text-white transition hover:bg-white/15 disabled:opacity-60"
                      >
                        Save name
                      </button>
                      <button
                        type="button"
                        onClick={() => updatePersonMutation.mutate({ is_hidden: !person.is_hidden })}
                        disabled={updatePersonMutation.isPending}
                        className="rounded-2xl border border-white/10 px-4 py-3 text-sm text-slate-200 transition hover:bg-white/10 disabled:opacity-60"
                      >
                        {person.is_hidden ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
                      </button>
                    </div>
                    <div className="space-y-1 text-xs text-slate-400">
                      <div>Thumbnail face: {person.thumbnail_face_id ?? "none"}</div>
                      <div>Thumbnail mode: {person.thumbnail_manually_set ? "manual" : "auto"}</div>
                    </div>
                  </div>
                </div>
              ) : null}
            </section>

            <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
              <div className="mb-4 flex items-center gap-3">
                <div className="rounded-2xl border border-cyan-400/20 bg-cyan-400/10 p-2 text-cyan-300">
                  <GitMerge className="h-4 w-4" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-white">Merge person</h2>
                  <p className="text-xs text-slate-400">Move non-excluded faces into another person.</p>
                </div>
              </div>
              <div className="space-y-3">
                <select
                  value={mergeTargetId}
                  onChange={(event) => setMergeTargetId(event.target.value)}
                  className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white outline-none focus:border-cyan-400/50"
                >
                  <option value="">Select target person</option>
                  {mergeOptions.map((option) => (
                    <option key={option.id} value={option.id}>
                      {(option.name?.trim() || "Unnamed person") + ` · ${option.asset_count} photos`}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => mergeMutation.mutate()}
                  disabled={!mergeTargetId || mergeMutation.isPending}
                  className="flex w-full items-center justify-center gap-2 rounded-2xl border border-cyan-400/30 bg-cyan-400/10 px-4 py-3 text-sm text-cyan-200 transition hover:bg-cyan-400/20 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {mergeMutation.isPending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <GitMerge className="h-4 w-4" />}
                  Merge into selected person
                </button>
                {mergeMutation.isError ? (
                  <p className="text-xs text-rose-300">{mergeMutation.error.message}</p>
                ) : null}
              </div>
            </section>
          </aside>

          <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
            <div className="mb-4 flex items-center justify-between gap-3 border-b border-white/10 pb-4">
              <div>
                <h2 className="text-lg font-semibold text-white">Photos containing this person</h2>
                <p className="text-sm text-slate-400">Excluded faces are not counted in this list.</p>
              </div>
              {assetsQuery.isFetching ? <LoaderCircle className="h-4 w-4 animate-spin text-slate-400" /> : null}
            </div>

            {assetsQuery.isLoading ? (
              <div className="flex min-h-[280px] items-center justify-center text-sm text-slate-400">
                <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
                Loading assets...
              </div>
            ) : null}

            {assetsQuery.isError ? (
              <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
                {assetsQuery.error.message}
              </div>
            ) : null}

            {!assetsQuery.isLoading && !assetsQuery.isError && assets.length === 0 ? (
              <div className="flex min-h-[280px] items-center justify-center rounded-3xl border border-dashed border-white/10 text-sm text-slate-500">
                No assets for this person yet.
              </div>
            ) : null}

            {assets.length > 0 ? (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {assets.map((asset) => (
                  <article key={asset.id} className="overflow-hidden rounded-3xl border border-white/10 bg-ink-800/70">
                    <button type="button" className="block w-full text-left" onClick={() => setSelectedAssetId(asset.id)}>
                      <div className="aspect-square overflow-hidden bg-black/20">
                        <img src={asset.small_thumbnail_url} alt={asset.description ?? asset.id} className="h-full w-full object-cover" />
                      </div>
                    </button>
                    <div className="space-y-2 p-4">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-white">{asset.description || asset.id.slice(0, 8)}</p>
                          <p className="text-xs text-slate-400">{formatDimension(asset)}</p>
                        </div>
                        <button
                          type="button"
                          onClick={() => updateThumbnailMutation.mutate(asset.id)}
                          disabled={updateThumbnailMutation.isPending}
                          className="rounded-2xl border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-[11px] text-amber-200 transition hover:bg-amber-400/20 disabled:opacity-60"
                        >
                          Use for thumbnail
                        </button>
                      </div>
                      <div className="flex flex-wrap gap-2 text-[11px] text-slate-300">
                        {asset.faces.slice(0, 4).map((face) => (
                          <span key={face.id} className="rounded-full border border-white/10 px-2.5 py-1">
                            {face.person?.name?.trim() || "Unnamed person"}
                          </span>
                        ))}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : null}
          </section>
        </div>
      </AppShell>

      <AssetDetailModal
        assetId={selectedAssetId}
        onClose={() => setSelectedAssetId(null)}
        thumbnailPersonId={personId}
      />
    </>
  );
}
