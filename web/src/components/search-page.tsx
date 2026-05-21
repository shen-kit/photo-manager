"use client";

import { useInfiniteQuery, useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, LoaderCircle, Search, Users, Workflow, X } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { AssetDetailModal } from "@/components/asset-detail-modal";
import { LoginScreen } from "@/components/login-screen";
import { useToast } from "@/components/toast-provider";
import { listPeople } from "@/lib/api/people";
import { searchAssets, triggerClipBackfill } from "@/lib/api/search";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import type { Person, SearchResultItem } from "@/lib/types";

const SEARCH_LIMIT = 24;

function formatDimension(asset: SearchResultItem) {
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

function personLabel(person: Person) {
  return person.name?.trim() || "Unnamed person";
}

export function SearchPage() {
  const { queryClient, isBootstrapping, setAccessReady, accessReady, currentUser } =
    useSessionBootstrap();
  const { pushToast } = useToast();
  const [inputValue, setInputValue] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [selectedPersonIds, setSelectedPersonIds] = useState<string[]>([]);
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const normalizedQuery = submittedQuery.trim();
  const hasFilters = normalizedQuery.length > 0 || selectedPersonIds.length > 0;

  const peopleQuery = useQuery({
    queryKey: ["people", "search-filters"],
    queryFn: () => listPeople(),
    enabled: accessReady,
  });

  const searchQuery = useInfiniteQuery({
    queryKey: ["search", normalizedQuery, selectedPersonIds],
    queryFn: ({ pageParam }) =>
      searchAssets(normalizedQuery, SEARCH_LIMIT, pageParam, selectedPersonIds),
    enabled: accessReady && hasFilters,
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  const backfillMutation = useMutation({
    mutationFn: () => triggerClipBackfill(false),
    onSuccess: (job) => {
      pushToast(`Backfill queued: ${job.id.slice(0, 8)}`, "success");
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error: Error) => {
      pushToast(error.message, "error");
    },
  });

  const results = useMemo(
    () => searchQuery.data?.pages.flatMap((page) => page.items) ?? [],
    [searchQuery.data?.pages],
  );
  const people = peopleQuery.data ?? [];
  const selectedPeople = people.filter((person) => selectedPersonIds.includes(person.id));

  if (isBootstrapping) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-4 text-sm text-slate-300">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Preparing search view...
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
        title="Search"
        description="Test CLIP search with optional people filters. Multi-person filters use AND semantics."
        headerActions={
          <button
            type="button"
            onClick={() => backfillMutation.mutate()}
            disabled={backfillMutation.isPending}
            className="flex items-center gap-2 rounded-2xl border border-cyan-400/30 bg-cyan-400/10 px-4 py-3 text-sm text-cyan-200 transition hover:bg-cyan-400/20 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {backfillMutation.isPending ? (
              <LoaderCircle className="h-4 w-4 animate-spin" />
            ) : (
              <Workflow className="h-4 w-4" />
            )}
            Backfill CLIP embeddings
          </button>
        }
      >
        <div className="grid gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
          <aside className="space-y-6">
            <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
              <div className="mb-4 flex items-center gap-3">
                <div className="rounded-2xl border border-white/10 bg-white/5 p-2 text-slate-300">
                  <Users className="h-4 w-4" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-white">People filters</h2>
                  <p className="text-xs text-slate-400">Photos containing all selected people.</p>
                </div>
              </div>

              {selectedPeople.length > 0 ? (
                <div className="mb-3 flex flex-wrap gap-2">
                  {selectedPeople.map((person) => (
                    <button
                      key={person.id}
                      type="button"
                      onClick={() =>
                        setSelectedPersonIds((current) => current.filter((value) => value !== person.id))
                      }
                      className="inline-flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-xs text-cyan-200"
                    >
                      {personLabel(person)}
                      <X className="h-3 w-3" />
                    </button>
                  ))}
                </div>
              ) : null}

              <div className="max-h-[420px] space-y-2 overflow-y-auto pr-1">
                {peopleQuery.isLoading ? (
                  <div className="text-sm text-slate-400">Loading people...</div>
                ) : null}
                {peopleQuery.isError ? (
                  <div className="text-sm text-rose-300">{peopleQuery.error.message}</div>
                ) : null}
                {people.map((person) => {
                  const checked = selectedPersonIds.includes(person.id);
                  return (
                    <label
                      key={person.id}
                      className="flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-slate-200"
                    >
                      <span className="min-w-0 flex-1 truncate">{personLabel(person)}</span>
                      <span className="text-xs text-slate-500">{person.asset_count}</span>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(event) => {
                          setSelectedPersonIds((current) =>
                            event.target.checked
                              ? [...current, person.id]
                              : current.filter((value) => value !== person.id),
                          );
                        }}
                        className="h-4 w-4 rounded border-white/10 bg-black/20 text-cyan-400 focus:ring-cyan-400/40"
                      />
                    </label>
                  );
                })}
              </div>
            </section>
          </aside>

          <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
            <div className="mb-5 flex flex-col gap-3 border-b border-white/10 pb-4">
              <div>
                <h2 className="text-lg font-semibold text-white">Asset Search</h2>
                <p className="text-sm text-slate-400">
                  Run text-only, people-only, or combined search.
                </p>
              </div>

              <form
                className="flex flex-col gap-3 md:flex-row"
                onSubmit={(event) => {
                  event.preventDefault();
                  const nextQuery = inputValue.trim();
                  if (!nextQuery && selectedPersonIds.length === 0) {
                    pushToast("Enter a query or select at least one person.", "error");
                    setSubmittedQuery("");
                    return;
                  }
                  setSubmittedQuery(nextQuery);
                }}
              >
                <input
                  value={inputValue}
                  onChange={(event) => setInputValue(event.target.value)}
                  placeholder="golden retriever on a beach"
                  className="min-w-0 flex-1 rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-400/50"
                />
                <button
                  type="submit"
                  disabled={searchQuery.isFetching}
                  className="flex items-center justify-center gap-2 rounded-2xl bg-white/10 px-4 py-3 text-sm font-medium text-white transition hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {searchQuery.isFetching ? (
                    <LoaderCircle className="h-4 w-4 animate-spin" />
                  ) : (
                    <Search className="h-4 w-4" />
                  )}
                  Search
                </button>
              </form>

              {backfillMutation.data ? (
                <p className="text-xs text-cyan-300">
                  Backfill job queued:{" "}
                  <Link href={`/jobs/${backfillMutation.data.id}`} className="underline">
                    {backfillMutation.data.id}
                  </Link>
                </p>
              ) : null}
            </div>

            {hasFilters ? (
              <div className="mb-5 text-sm text-slate-400">
                {searchQuery.data
                  ? `${results.length} result${results.length === 1 ? "" : "s"} loaded${normalizedQuery ? ` for "${normalizedQuery}"` : ""}`
                  : selectedPersonIds.length > 0 && !normalizedQuery
                    ? "Searching by selected people..."
                    : `Searching for "${normalizedQuery}"`}
              </div>
            ) : null}

            {searchQuery.isLoading ? (
              <div className="flex min-h-[280px] items-center justify-center text-sm text-slate-400">
                <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
                Searching assets...
              </div>
            ) : null}

            {searchQuery.isError ? (
              <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
                {searchQuery.error.message}
              </div>
            ) : null}

            {!hasFilters ? (
              <div className="flex min-h-[280px] items-center justify-center rounded-3xl border border-dashed border-white/10 text-sm text-slate-500">
                Enter a query or select people to search.
              </div>
            ) : null}

            {!searchQuery.isLoading && !searchQuery.isError && hasFilters && results.length === 0 ? (
              <div className="flex min-h-[280px] flex-col items-center justify-center gap-3 rounded-3xl border border-dashed border-white/10 text-sm text-slate-500">
                <AlertTriangle className="h-5 w-5 text-slate-600" />
                No matching assets found.
              </div>
            ) : null}

            {results.length > 0 ? (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                {results.map((asset) => (
                  <article
                    key={asset.id}
                    className="group overflow-hidden rounded-3xl border border-white/10 bg-ink-800/70 transition hover:border-white/20 hover:bg-ink-800"
                  >
                    <button
                      type="button"
                      className="block w-full text-left"
                      onClick={() => setSelectedAssetId(asset.id)}
                    >
                      <div className="relative aspect-square overflow-hidden">
                        <div className="absolute inset-0" style={placeholderStyle(asset.blurhash ?? asset.id)} />
                          <img
                            src={asset.small_thumbnail_url}
                            alt={asset.id}
                            className="relative h-full w-full object-cover transition duration-300 group-hover:scale-[1.02]"
                          />
                      </div>
                    </button>
                    <div className="space-y-3 p-4">
                      <div>
                        <p className="truncate text-sm font-semibold text-white">
                          {asset.id.slice(0, 8)}
                        </p>
                        <p className="mt-1 text-xs text-slate-400">{formatDimension(asset)}</p>
                        <p className="mt-1 text-[11px] text-slate-500">
                          {asset.media_kind} · {asset.timeline_day}
                          {asset.duration_seconds ? ` · ${asset.duration_seconds.toFixed(1)}s` : ""}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2 text-[11px]">
                        <span className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-2.5 py-1 text-cyan-200">
                          Score {asset.score.toFixed(3)}
                        </span>
                        <span className="rounded-full border border-white/10 px-2.5 py-1 text-slate-300">
                          Distance {asset.distance.toFixed(3)}
                        </span>
                        <span className="rounded-full border border-white/10 px-2.5 py-1 text-slate-300">
                          {asset.mime_type}
                        </span>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : null}

            {searchQuery.hasNextPage ? (
              <div className="mt-6 flex justify-center">
                <button
                  type="button"
                  onClick={() => searchQuery.fetchNextPage()}
                  disabled={searchQuery.isFetchingNextPage}
                  className="rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-3 text-sm text-slate-200 transition hover:bg-white/[0.07] disabled:opacity-60"
                >
                  {searchQuery.isFetchingNextPage ? "Loading…" : "Load more"}
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
