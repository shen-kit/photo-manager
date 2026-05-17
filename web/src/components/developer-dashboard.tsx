"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  DatabaseZap,
  LoaderCircle,
  LogOut,
  SearchCheck,
  Star,
  Trash2,
  Upload,
} from "lucide-react";
import { useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { AssetDetailModal } from "@/components/asset-detail-modal";
import { FileDropzone } from "@/components/file-dropzone";
import { LoginScreen } from "@/components/login-screen";
import { useToast } from "@/components/toast-provider";
import { deleteAsset, ingestPath, listAssets, scanAssets, updateAsset, uploadAsset } from "@/lib/api/assets";
import { fetchCurrentUser, getStoredUser, login, logout, refreshSession } from "@/lib/api/auth";
import { clearSession, loadSession } from "@/lib/auth-store";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import type { AssetListItem, AssetListResponse } from "@/lib/types";

const PAGE_SIZE = 24;

function formatDimension(asset: AssetListItem) {
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

export function DeveloperDashboard() {
  const { queryClient, isBootstrapping, accessReady, setAccessReady, currentUser } =
    useSessionBootstrap();
  const { pushToast } = useToast();
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const [pathValue, setPathValue] = useState("");

  const assetsQuery = useInfiniteQuery({
    queryKey: ["assets"],
    queryFn: ({ pageParam }) => listAssets(pageParam, PAGE_SIZE),
    enabled: accessReady,
    initialPageParam: 1,
    getNextPageParam: (lastPage) => {
      const loaded = lastPage.page * lastPage.page_size;
      return loaded < lastPage.total ? lastPage.page + 1 : undefined;
    },
  });

  const assetPages = assetsQuery.data?.pages ?? [];
  const assets = useMemo(() => assetPages.flatMap((page) => page.items), [assetPages]);
  const totalAssets = assetPages[0]?.total ?? 0;

  const scanMutation = useMutation({
    mutationFn: scanAssets,
    onSuccess: async (data) => {
      pushToast(`Scan job queued: ${data.id.slice(0, 8)}`, "success");
    },
    onError: (error: Error) => pushToast(error.message, "error"),
  });

  const uploadMutation = useMutation({
    mutationFn: async (files: File[]) => {
      for (const file of files) {
        await uploadAsset(file);
      }
    },
    onSuccess: async () => {
      pushToast("Upload complete", "success");
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
    onError: (error: Error) => pushToast(error.message, "error"),
  });

  const ingestMutation = useMutation({
    mutationFn: ingestPath,
    onSuccess: async () => {
      setPathValue("");
      pushToast("Path ingested", "success");
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
    onError: (error: Error) => pushToast(error.message, "error"),
  });

  const favoriteMutation = useMutation({
    mutationFn: ({ assetId, nextValue }: { assetId: string; nextValue: boolean }) =>
      updateAsset(assetId, { is_favorite: nextValue }),
    onMutate: async ({ assetId, nextValue }) => {
      await queryClient.cancelQueries({ queryKey: ["assets"] });
      const previous = queryClient.getQueryData(["assets"]);

      queryClient.setQueryData(["assets"], (current: { pages: AssetListResponse[]; pageParams: number[] } | undefined) => {
        if (!current) {
          return current;
        }
        return {
          ...current,
          pages: current.pages.map((page) => ({
            ...page,
            items: page.items.map((asset) =>
              asset.id === assetId ? { ...asset, is_favorite: nextValue } : asset,
            ),
          })),
        };
      });

      return { previous };
    },
    onError: (error: Error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(["assets"], context.previous);
      }
      pushToast(error.message, "error");
    },
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteAsset,
    onMutate: async (assetId) => {
      await queryClient.cancelQueries({ queryKey: ["assets"] });
      const previous = queryClient.getQueryData(["assets"]);

      queryClient.setQueryData(["assets"], (current: { pages: AssetListResponse[]; pageParams: number[] } | undefined) => {
        if (!current) {
          return current;
        }

        const nextPages = current.pages.map((page) => ({
          ...page,
          total: Math.max(page.total - 1, 0),
          items: page.items.filter((asset) => asset.id !== assetId),
        }));

        return {
          ...current,
          pages: nextPages,
        };
      });

      return { previous };
    },
    onSuccess: () => {
      pushToast("Asset deleted", "info");
    },
    onError: (error: Error, _assetId, context) => {
      if (context?.previous) {
        queryClient.setQueryData(["assets"], context.previous);
      }
      pushToast(error.message, "error");
    },
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
  });

  if (isBootstrapping) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-4 text-sm text-slate-300">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Preparing dashboard...
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
          await queryClient.invalidateQueries({ queryKey: ["assets"] });
        }}
      />
    );
  }

  return (
    <>
      <AppShell
        currentUser={currentUser}
        title="Developer Dashboard"
        description="Manage ingestion and inspect assets from a single screen."
        headerActions={
          <button
            type="button"
            onClick={() => scanMutation.mutate()}
            disabled={scanMutation.isPending}
            className="flex items-center gap-2 rounded-2xl border border-cyan-400/30 bg-cyan-400/10 px-4 py-3 text-sm text-cyan-200 transition hover:bg-cyan-400/20 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {scanMutation.isPending ? (
              <LoaderCircle className="h-4 w-4 animate-spin" />
            ) : (
              <SearchCheck className="h-4 w-4" />
            )}
            Bulk Scan
          </button>
        }
      >
        <div className="grid gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
            <aside className="space-y-6">
              <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
                <div className="mb-4 flex items-center gap-3">
                  <div className="rounded-2xl border border-cyan-400/20 bg-cyan-400/10 p-2 text-cyan-300">
                    <Upload className="h-4 w-4" />
                  </div>
                  <div>
                    <h2 className="text-sm font-semibold text-white">Direct Upload</h2>
                    <p className="text-xs text-slate-400">Multipart upload to the originals library.</p>
                  </div>
                </div>
                <FileDropzone disabled={uploadMutation.isPending} onSelect={(files) => uploadMutation.mutate(files)} />
                {uploadMutation.isPending ? <p className="mt-3 text-xs text-slate-500">Uploading queued files...</p> : null}
              </section>

              <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
                <div className="mb-4 flex items-center gap-3">
                  <div className="rounded-2xl border border-amber-400/20 bg-amber-400/10 p-2 text-amber-300">
                    <DatabaseZap className="h-4 w-4" />
                  </div>
                  <div>
                    <h2 className="text-sm font-semibold text-white">Path Ingest</h2>
                    <p className="text-xs text-slate-400">Submit a server-relative path into `/media/originals`.</p>
                  </div>
                </div>
                <form
                  className="space-y-3"
                  onSubmit={(event) => {
                    event.preventDefault();
                    ingestMutation.mutate(pathValue);
                  }}
                >
                  <textarea
                    value={pathValue}
                    onChange={(event) => setPathValue(event.target.value)}
                    rows={4}
                    placeholder="2026/05/family-trip/photo-001.jpg"
                    className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-400/50"
                  />
                  <button
                    type="submit"
                    disabled={ingestMutation.isPending || !pathValue.trim()}
                    className="flex w-full items-center justify-center gap-2 rounded-2xl bg-white/10 px-4 py-3 text-sm font-medium text-white transition hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {ingestMutation.isPending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <DatabaseZap className="h-4 w-4" />}
                    Ingest Path
                  </button>
                </form>
              </section>
            </aside>

            <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
              <div className="mb-5 flex flex-col gap-2 border-b border-white/10 pb-4 md:flex-row md:items-end md:justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-white">Asset Gallery</h2>
                  <p className="text-sm text-slate-400">
                    {assets.length} loaded of {totalAssets} assets
                  </p>
                </div>
                {assetsQuery.isFetching ? <p className="text-xs text-cyan-300">Syncing asset list...</p> : null}
              </div>

              {assetsQuery.isLoading ? (
                <div className="flex min-h-[280px] items-center justify-center text-sm text-slate-400">
                  <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
                  Loading assets...
                </div>
              ) : null}

              {assetsQuery.isError ? (
                <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
                  {(assetsQuery.error as Error).message}
                </div>
              ) : null}

              {assets.length > 0 ? (
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                  {assets.map((asset) => (
                    <article
                      key={asset.id}
                      className="group overflow-hidden rounded-3xl border border-white/10 bg-ink-800/70 transition hover:border-white/20 hover:bg-ink-800"
                    >
                      <button type="button" className="block w-full text-left" onClick={() => setSelectedAssetId(asset.id)}>
                        <div className="relative aspect-square overflow-hidden">
                          <div className="absolute inset-0" style={placeholderStyle(asset.blurhash ?? asset.id)} />
                          <img
                            src={asset.small_thumbnail_url}
                            alt={asset.description ?? asset.id}
                            className="relative h-full w-full object-cover transition duration-300 group-hover:scale-[1.02]"
                          />
                        </div>
                      </button>
                      <div className="space-y-3 p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-white">{asset.description || asset.id.slice(0, 8)}</p>
                            <p className="mt-1 text-xs text-slate-400">{formatDimension(asset)}</p>
                          </div>
                          <div className="flex items-center gap-1">
                            <button
                              type="button"
                              className={`rounded-full p-2 transition ${
                                asset.is_favorite ? "bg-amber-400/15 text-amber-300" : "text-slate-500 hover:bg-white/10 hover:text-slate-200"
                              }`}
                              onClick={() => favoriteMutation.mutate({ assetId: asset.id, nextValue: !asset.is_favorite })}
                            >
                              <Star className={`h-4 w-4 ${asset.is_favorite ? "fill-current" : ""}`} />
                            </button>
                            <button
                              type="button"
                              className="rounded-full p-2 text-slate-500 transition hover:bg-rose-500/15 hover:text-rose-300"
                              onClick={() => deleteMutation.mutate(asset.id)}
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </div>

                        <div className="flex flex-wrap gap-2">
                          {asset.tags.slice(0, 3).map((tag) => (
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
                      </div>
                    </article>
                  ))}
                </div>
              ) : null}

              {!assetsQuery.isLoading && assets.length === 0 && !assetsQuery.isError ? (
                <div className="flex min-h-[280px] items-center justify-center rounded-3xl border border-dashed border-white/10 text-sm text-slate-500">
                  No assets available yet.
                </div>
              ) : null}

              {assetsQuery.hasNextPage ? (
                <div className="mt-6 flex justify-center">
                  <button
                    type="button"
                    onClick={() => assetsQuery.fetchNextPage()}
                    disabled={assetsQuery.isFetchingNextPage}
                    className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-3 text-sm text-slate-200 transition hover:bg-white/[0.07] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {assetsQuery.isFetchingNextPage ? <LoaderCircle className="h-4 w-4 animate-spin" /> : null}
                    Load More
                  </button>
                </div>
              ) : null}
            </section>
          </div>
      </AppShell>

      <AssetDetailModal assetId={selectedAssetId} onClose={() => setSelectedAssetId(null)} />
    </>
  );
}
