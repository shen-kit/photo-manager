"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckSquare,
  LoaderCircle,
  RefreshCcw,
  RotateCcw,
  Square,
  Trash2,
} from "lucide-react";
import { useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { LoginScreen } from "@/components/login-screen";
import { TrashDetailModal } from "@/components/trash-detail-modal";
import { useToast } from "@/components/toast-provider";
import { listTrashAssets, restoreTrashAsset, restoreTrashAssets } from "@/lib/api/trash";
import { formatDateTime } from "@/lib/format";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import type { TrashAssetListItem, TrashRestoreFailure, TrashSort } from "@/lib/types";

const PAGE_SIZE = 24;

const SORT_OPTIONS: Array<{ value: TrashSort; label: string }> = [
  { value: "deleted_at_desc", label: "Deletion date: newest first" },
  { value: "deleted_at_asc", label: "Deletion date: oldest first" },
  { value: "taken_at_desc", label: "Photo taken: newest first" },
  { value: "taken_at_asc", label: "Photo taken: oldest first" },
];

function formatDimension(asset: TrashAssetListItem) {
  if (!asset.width || !asset.height) {
    return "Unknown size";
  }
  return `${asset.width} x ${asset.height}`;
}

function placeholderStyle(seed: string) {
  let hash = 0;
  for (let index = 0; index < seed.length; index += 1) {
    hash = seed.charCodeAt(index) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  return {
    background: `linear-gradient(135deg, hsl(${hue} 65% 22%), hsl(${(hue + 48) % 360} 70% 32%))`,
  };
}

function assetTitle(asset: TrashAssetListItem) {
  return asset.description?.trim() || asset.id.slice(0, 8);
}

export function TrashPage() {
  const { queryClient, isBootstrapping, setAccessReady, accessReady, currentUser } =
    useSessionBootstrap();
  const { pushToast } = useToast();
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<TrashSort>("deleted_at_desc");
  const [selectedAssetIds, setSelectedAssetIds] = useState<string[]>([]);
  const [detailAssetId, setDetailAssetId] = useState<string | null>(null);
  const [bulkFailures, setBulkFailures] = useState<TrashRestoreFailure[]>([]);

  const trashQuery = useQuery({
    queryKey: ["trash-assets", page, sort],
    queryFn: () => listTrashAssets(page, PAGE_SIZE, sort),
    enabled: accessReady,
  });

  const singleRestoreMutation = useMutation({
    mutationFn: restoreTrashAsset,
    onSuccess: async (_, restoredAssetId) => {
      pushToast("Asset restored", "success");
      setSelectedAssetIds((current) => current.filter((assetId) => assetId !== restoredAssetId));
      await queryClient.invalidateQueries({ queryKey: ["trash-assets"] });
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
      await queryClient.invalidateQueries({ queryKey: ["search"] });
    },
    onError: (error: Error) => pushToast(error.message, "error"),
  });

  const bulkRestoreMutation = useMutation({
    mutationFn: restoreTrashAssets,
    onSuccess: async (response) => {
      setBulkFailures(response.failures);
      if (response.restored > 0) {
        pushToast(`Restored ${response.restored} asset${response.restored === 1 ? "" : "s"}`, "success");
      }
      if (response.failed > 0) {
        pushToast(`${response.failed} restore failure${response.failed === 1 ? "" : "s"}`, "error");
      }
      const restoredIds = new Set(response.items.map((item) => item.asset.id));
      setSelectedAssetIds((current) => current.filter((assetId) => !restoredIds.has(assetId)));
      await queryClient.invalidateQueries({ queryKey: ["trash-assets"] });
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
      await queryClient.invalidateQueries({ queryKey: ["search"] });
    },
    onError: (error: Error) => pushToast(error.message, "error"),
  });

  const items = trashQuery.data?.items ?? [];
  const total = trashQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const allVisibleSelected = items.length > 0 && items.every((item) => selectedAssetIds.includes(item.id));
  const selectedCount = selectedAssetIds.length;

  const selectedOnPage = useMemo(
    () => items.filter((item) => selectedAssetIds.includes(item.id)),
    [items, selectedAssetIds],
  );

  const toggleSelected = (assetId: string) => {
    setSelectedAssetIds((current) =>
      current.includes(assetId)
        ? current.filter((id) => id !== assetId)
        : [...current, assetId],
    );
  };

  const toggleSelectPage = () => {
    setSelectedAssetIds((current) => {
      const visibleIds = items.map((item) => item.id);
      if (allVisibleSelected) {
        return current.filter((id) => !visibleIds.includes(id));
      }
      return Array.from(new Set([...current, ...visibleIds]));
    });
  };

  const handleBulkRestore = () => {
    if (selectedAssetIds.length === 0) {
      pushToast("Select at least one asset to restore", "info");
      return;
    }
    bulkRestoreMutation.mutate({ asset_ids: selectedAssetIds });
  };

  if (isBootstrapping) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-4 text-sm text-slate-300">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Preparing trash view...
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
        title="Trash"
        description="Development UI for browsing soft-deleted assets and exercising restore flows."
        headerActions={
          <button
            type="button"
            onClick={() => void trashQuery.refetch()}
            className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white transition hover:bg-white/10"
          >
            <RefreshCcw className="h-4 w-4" />
            Refresh
          </button>
        }
      >
        <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
          <aside className="space-y-6">
            <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
              <div className="mb-4 flex items-center gap-3">
                <div className="rounded-2xl border border-amber-400/20 bg-amber-400/10 p-2 text-amber-300">
                  <Trash2 className="h-4 w-4" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-white">Filters</h2>
                  <p className="text-xs text-slate-400">Trash results stay hidden from normal asset views.</p>
                </div>
              </div>
              <div className="space-y-3">
                <label className="block">
                  <span className="mb-1 block text-xs text-slate-400">Sort</span>
                  <select
                    value={sort}
                    onChange={(event) => {
                      setSort(event.target.value as TrashSort);
                      setPage(1);
                    }}
                    className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white outline-none focus:border-cyan-400/50"
                  >
                    {SORT_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  onClick={toggleSelectPage}
                  disabled={items.length === 0}
                  className="flex w-full items-center justify-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {allVisibleSelected ? <CheckSquare className="h-4 w-4" /> : <Square className="h-4 w-4" />}
                  {allVisibleSelected ? "Clear page selection" : "Select page"}
                </button>
              </div>
            </section>

            <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
              <div className="mb-4 flex items-center gap-3">
                <div className="rounded-2xl border border-emerald-400/20 bg-emerald-400/10 p-2 text-emerald-300">
                  <RotateCcw className="h-4 w-4" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-white">Restore</h2>
                  <p className="text-xs text-slate-400">{selectedCount} selected on this view.</p>
                </div>
              </div>
              <div className="space-y-3">
                <button
                  type="button"
                  onClick={handleBulkRestore}
                  disabled={selectedCount === 0 || bulkRestoreMutation.isPending}
                  className="flex w-full items-center justify-center gap-2 rounded-2xl border border-emerald-400/30 bg-emerald-400/10 px-4 py-3 text-sm text-emerald-200 transition hover:bg-emerald-400/20 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {bulkRestoreMutation.isPending ? (
                    <LoaderCircle className="h-4 w-4 animate-spin" />
                  ) : (
                    <RotateCcw className="h-4 w-4" />
                  )}
                  Restore selected
                </button>
                {selectedOnPage.length > 0 ? (
                  <div className="rounded-2xl border border-white/10 bg-black/20 p-3 text-xs text-slate-300">
                    {selectedOnPage.length} selected on this page
                  </div>
                ) : null}
                {bulkFailures.length > 0 ? (
                  <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-200">
                    <p className="font-medium">Bulk restore issues</p>
                    <ul className="mt-2 space-y-1">
                      {bulkFailures.map((failure) => (
                        <li key={failure.asset_id}>
                          {failure.asset_id.slice(0, 8)}: {failure.detail}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            </section>
          </aside>

          <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
            <div className="mb-5 flex flex-col gap-2 border-b border-white/10 pb-4 md:flex-row md:items-end md:justify-between">
              <div>
                <h2 className="text-lg font-semibold text-white">Deleted assets</h2>
                <p className="text-sm text-slate-400">
                  Page {page} of {totalPages} · {total} total
                </p>
              </div>
              {trashQuery.isFetching ? <p className="text-xs text-cyan-300">Syncing trash list...</p> : null}
            </div>

            {trashQuery.isLoading ? (
              <div className="flex min-h-[280px] items-center justify-center text-sm text-slate-400">
                <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
                Loading deleted assets...
              </div>
            ) : null}

            {trashQuery.isError ? (
              <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
                {trashQuery.error.message}
              </div>
            ) : null}

            {!trashQuery.isLoading && !trashQuery.isError && items.length === 0 ? (
              <div className="flex min-h-[280px] items-center justify-center rounded-3xl border border-dashed border-white/10 text-sm text-slate-500">
                Trash is empty.
              </div>
            ) : null}

            {items.length > 0 ? (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                {items.map((asset) => {
                  const checked = selectedAssetIds.includes(asset.id);
                  return (
                    <article
                      key={asset.id}
                      className="group overflow-hidden rounded-3xl border border-white/10 bg-ink-800/70 transition hover:border-white/20 hover:bg-ink-800"
                    >
                      <div className="relative aspect-square overflow-hidden">
                        <button
                          type="button"
                          onClick={() => toggleSelected(asset.id)}
                          className="absolute left-3 top-3 z-10 rounded-full border border-white/20 bg-black/45 p-2 text-white transition hover:bg-black/70"
                        >
                          {checked ? <CheckSquare className="h-4 w-4 text-emerald-300" /> : <Square className="h-4 w-4" />}
                        </button>
                        <button type="button" className="block h-full w-full text-left" onClick={() => setDetailAssetId(asset.id)}>
                          <div className="absolute inset-0" style={placeholderStyle(asset.blurhash ?? asset.id)} />
                          <img
                            src={asset.small_thumbnail_url}
                            alt={assetTitle(asset)}
                            className="relative h-full w-full object-cover transition duration-300 group-hover:scale-[1.02]"
                          />
                        </button>
                      </div>
                      <div className="space-y-3 p-4">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-white">{assetTitle(asset)}</p>
                          <p className="mt-1 text-xs text-slate-400">{formatDimension(asset)}</p>
                        </div>
                        <div className="space-y-1 text-xs text-slate-400">
                          <p>Deleted: {formatDateTime(asset.deleted_at)}</p>
                          <p>Taken: {formatDateTime(asset.captured_at)}</p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {asset.tags.slice(0, 2).map((tag) => (
                            <span key={tag.id} className="rounded-full border border-white/10 px-2.5 py-1 text-[11px] text-slate-300">
                              {tag.name}
                            </span>
                          ))}
                          {asset.faces.length > 0 ? (
                            <span className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-2.5 py-1 text-[11px] text-cyan-200">
                              {asset.faces.length} face{asset.faces.length === 1 ? "" : "s"}
                            </span>
                          ) : null}
                        </div>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => setDetailAssetId(asset.id)}
                            className="flex-1 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white transition hover:bg-white/10"
                          >
                            Details
                          </button>
                          <button
                            type="button"
                            onClick={() => singleRestoreMutation.mutate(asset.id)}
                            disabled={singleRestoreMutation.isPending || bulkRestoreMutation.isPending}
                            className="flex items-center gap-2 rounded-2xl border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-sm text-emerald-200 transition hover:bg-emerald-400/20 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            {singleRestoreMutation.isPending && singleRestoreMutation.variables === asset.id ? (
                              <LoaderCircle className="h-4 w-4 animate-spin" />
                            ) : (
                              <RotateCcw className="h-4 w-4" />
                            )}
                            Restore
                          </button>
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : null}

            <div className="mt-6 flex items-center justify-between">
              <button
                type="button"
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                disabled={page <= 1 || trashQuery.isFetching}
                className="rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-3 text-sm text-slate-200 transition hover:bg-white/[0.07] disabled:cursor-not-allowed disabled:opacity-60"
              >
                Previous
              </button>
              <p className="text-sm text-slate-400">
                {items.length} shown
              </p>
              <button
                type="button"
                onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                disabled={page >= totalPages || trashQuery.isFetching}
                className="rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-3 text-sm text-slate-200 transition hover:bg-white/[0.07] disabled:cursor-not-allowed disabled:opacity-60"
              >
                Next
              </button>
            </div>
          </section>
        </div>
      </AppShell>

      <TrashDetailModal assetId={detailAssetId} onClose={() => setDetailAssetId(null)} />
    </>
  );
}
