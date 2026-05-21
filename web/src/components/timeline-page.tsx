"use client";

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { CalendarDays, LoaderCircle } from "lucide-react";
import { useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { AssetDetailModal } from "@/components/asset-detail-modal";
import { LoginScreen } from "@/components/login-screen";
import { listAssets } from "@/lib/api/assets";
import { listPeople } from "@/lib/api/people";
import { listTimelineDays, listTimelineMonths } from "@/lib/api/timeline";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import type { MediaKind, Person } from "@/lib/types";

const PAGE_SIZE = 24;

function personLabel(person: Person) {
  return person.name?.trim() || "Unnamed person";
}

export function TimelinePage() {
  const { queryClient, isBootstrapping, setAccessReady, accessReady, currentUser } =
    useSessionBootstrap();
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const [selectedPersonIds, setSelectedPersonIds] = useState<string[]>([]);
  const [mediaKind, setMediaKind] = useState<MediaKind | "all">("all");
  const [selectedMonth, setSelectedMonth] = useState<string | null>(null);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);

  const peopleQuery = useQuery({
    queryKey: ["people", "timeline-filters"],
    queryFn: () => listPeople(),
    enabled: accessReady,
  });

  const monthsQuery = useQuery({
    queryKey: ["timeline", "months", mediaKind, selectedPersonIds],
    queryFn: () =>
      listTimelineMonths({
        mediaKind: mediaKind === "all" ? undefined : mediaKind,
        personIds: selectedPersonIds,
      }),
    enabled: accessReady,
  });

  const daysQuery = useQuery({
    queryKey: ["timeline", "days", selectedMonth, mediaKind, selectedPersonIds],
    queryFn: () =>
      listTimelineDays(selectedMonth as string, {
        mediaKind: mediaKind === "all" ? undefined : mediaKind,
        personIds: selectedPersonIds,
      }),
    enabled: accessReady && Boolean(selectedMonth),
  });

  const assetsQuery = useInfiniteQuery({
    queryKey: ["assets", "timeline", selectedMonth, selectedDay, mediaKind, selectedPersonIds],
    queryFn: ({ pageParam }) =>
      listAssets({
        limit: PAGE_SIZE,
        cursor: pageParam,
        mediaKind: mediaKind === "all" ? undefined : mediaKind,
        month: selectedDay ? undefined : selectedMonth ?? undefined,
        day: selectedDay ?? undefined,
        personIds: selectedPersonIds,
      }),
    enabled: accessReady && Boolean(selectedMonth || selectedDay),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  const monthBuckets = monthsQuery.data ?? [];
  const dayBuckets = daysQuery.data ?? [];
  const assetItems = useMemo(
    () => assetsQuery.data?.pages.flatMap((page) => page.items) ?? [],
    [assetsQuery.data?.pages],
  );
  const people = peopleQuery.data ?? [];

  if (isBootstrapping) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-4 text-sm text-slate-300">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Preparing timeline view...
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
        title="Timeline"
        description="Test month/day bucket APIs and date-filtered cursor browsing."
        headerActions={
          <div className="flex items-center gap-2 rounded-2xl border border-cyan-400/20 bg-cyan-400/10 px-4 py-3 text-sm text-cyan-200">
            <CalendarDays className="h-4 w-4" />
            Timeline explorer
          </div>
        }
      >
        <div className="grid gap-6 lg:grid-cols-[300px_300px_minmax(0,1fr)]">
          <aside className="space-y-4 rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
            <div>
              <h2 className="text-sm font-semibold text-white">Filters</h2>
              <p className="text-xs text-slate-400">Filters apply to buckets and asset slices.</p>
            </div>
            <select
              value={mediaKind}
              onChange={(event) => setMediaKind(event.target.value as MediaKind | "all")}
              className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white outline-none focus:border-cyan-400/50"
            >
              <option value="all">All media</option>
              <option value="image">Images</option>
              <option value="video">Videos</option>
            </select>
            <div className="max-h-[420px] space-y-2 overflow-y-auto pr-1">
              {people.map((person) => {
                const checked = selectedPersonIds.includes(person.id);
                return (
                  <label
                    key={person.id}
                    className="flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-slate-200"
                  >
                    <span className="min-w-0 flex-1 truncate">{personLabel(person)}</span>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) =>
                        setSelectedPersonIds((current) =>
                          event.target.checked
                            ? [...current, person.id]
                            : current.filter((value) => value !== person.id),
                        )
                      }
                      className="h-4 w-4 rounded border-white/10 bg-black/20 text-cyan-400 focus:ring-cyan-400/40"
                    />
                  </label>
                );
              })}
            </div>
          </aside>

          <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
            <div className="mb-4">
              <h2 className="text-sm font-semibold text-white">Months</h2>
              <p className="text-xs text-slate-400">Jump to a month bucket.</p>
            </div>
            <div className="space-y-2">
              {monthsQuery.isLoading ? <p className="text-sm text-slate-400">Loading months…</p> : null}
              {monthBuckets.map((bucket) => (
                <button
                  key={bucket.month}
                  type="button"
                  onClick={() => {
                    setSelectedMonth(bucket.month);
                    setSelectedDay(null);
                  }}
                  className={`flex w-full items-center justify-between rounded-2xl border px-3 py-3 text-left text-sm transition ${
                    selectedMonth === bucket.month
                      ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-100"
                      : "border-white/10 bg-black/20 text-slate-200 hover:bg-white/[0.06]"
                  }`}
                >
                  <span>{bucket.month}</span>
                  <span className="text-xs text-slate-400">{bucket.asset_count}</span>
                </button>
              ))}
            </div>
          </section>

          <section className="rounded-[28px] border border-white/10 bg-black/25 p-5 shadow-panel backdrop-blur">
            <div className="mb-4 flex items-center justify-between gap-3 border-b border-white/10 pb-4">
              <div>
                <h2 className="text-lg font-semibold text-white">Day buckets and assets</h2>
                <p className="text-sm text-slate-400">
                  {selectedDay
                    ? `Browsing ${selectedDay}`
                    : selectedMonth
                      ? `Select a day in ${selectedMonth} or browse the full month`
                      : "Select a month to load day buckets and assets"}
                </p>
              </div>
              {(daysQuery.isFetching || assetsQuery.isFetching) ? (
                <LoaderCircle className="h-4 w-4 animate-spin text-slate-400" />
              ) : null}
            </div>

            {selectedMonth ? (
              <div className="mb-5 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => setSelectedDay(null)}
                  className={`rounded-full border px-3 py-1 text-xs ${
                    !selectedDay
                      ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-100"
                      : "border-white/10 text-slate-300"
                  }`}
                >
                  Whole month
                </button>
                {dayBuckets.map((bucket) => (
                  <button
                    key={bucket.day}
                    type="button"
                    onClick={() => setSelectedDay(bucket.day)}
                    className={`rounded-full border px-3 py-1 text-xs ${
                      selectedDay === bucket.day
                        ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-100"
                        : "border-white/10 text-slate-300"
                    }`}
                  >
                    {bucket.day} · {bucket.asset_count}
                  </button>
                ))}
              </div>
            ) : null}

            {assetItems.length > 0 ? (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {assetItems.map((asset) => (
                  <article key={asset.id} className="overflow-hidden rounded-3xl border border-white/10 bg-ink-800/70">
                    <button type="button" className="block w-full text-left" onClick={() => setSelectedAssetId(asset.id)}>
                      <div className="aspect-square overflow-hidden bg-black/20">
                        <img src={asset.small_thumbnail_url} alt={asset.id} className="h-full w-full object-cover" />
                      </div>
                    </button>
                    <div className="space-y-2 p-4">
                      <p className="truncate text-sm font-semibold text-white">{asset.id.slice(0, 8)}</p>
                      <p className="text-xs text-slate-400">{asset.media_kind} · {asset.timeline_day}</p>
                    </div>
                  </article>
                ))}
              </div>
            ) : null}

            {!assetsQuery.isLoading && selectedMonth && assetItems.length === 0 ? (
              <div className="flex min-h-[220px] items-center justify-center rounded-3xl border border-dashed border-white/10 text-sm text-slate-500">
                No assets for the current timeline selection.
              </div>
            ) : null}

            {assetsQuery.hasNextPage ? (
              <div className="mt-6 flex justify-center">
                <button
                  type="button"
                  onClick={() => assetsQuery.fetchNextPage()}
                  disabled={assetsQuery.isFetchingNextPage}
                  className="rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-3 text-sm text-slate-200 transition hover:bg-white/[0.07] disabled:opacity-60"
                >
                  {assetsQuery.isFetchingNextPage ? "Loading…" : "Load more"}
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
