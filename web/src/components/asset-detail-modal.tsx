"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Eye,
  EyeOff,
  LoaderCircle,
  ScanFace,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { AuthenticatedPreview } from "@/components/authenticated-preview";
import { useToast } from "@/components/toast-provider";
import { addAssetTag, ensureAssetPreviews, getAsset, removeAssetTag } from "@/lib/api/assets";
import { getAssetFaces, triggerAssetFaceProcessing, updateAssetFace } from "@/lib/api/faces";
import { listPeople, updatePersonThumbnail } from "@/lib/api/people";
import { listTags } from "@/lib/api/tags";
import type { AssetFace, AssetPreviewEnsureItem, Person } from "@/lib/types";

type AssetDetailModalNavigationItem = {
  id: string;
  mime_type: string;
};

type AssetDetailModalProps = {
  assetId: string | null;
  onClose: () => void;
  onSelectAsset?: (assetId: string) => void;
  navigationItems?: AssetDetailModalNavigationItem[];
  thumbnailPersonId?: string | null;
};

function faceBoxStyle(face: AssetFace) {
  const box = face.bounding_box;
  if (!box || box.image_width <= 0 || box.image_height <= 0) {
    return null;
  }

  return {
    left: `${(box.x / box.image_width) * 100}%`,
    top: `${(box.y / box.image_height) * 100}%`,
    width: `${(box.width / box.image_width) * 100}%`,
    height: `${(box.height / box.image_height) * 100}%`,
  };
}

function personLabel(person: Person) {
  return person.name?.trim() || "Unnamed person";
}

function mergePreviewItems(
  current: Record<string, AssetPreviewEnsureItem>,
  items: AssetPreviewEnsureItem[],
) {
  if (items.length === 0) {
    return current;
  }

  const next = { ...current };
  for (const item of items) {
    next[item.asset_id] = item;
  }
  return next;
}

export function AssetDetailModal({
  assetId,
  onClose,
  onSelectAsset,
  navigationItems = [],
  thumbnailPersonId = null,
}: AssetDetailModalProps) {
  const [mounted, setMounted] = useState(false);
  const [forceFaceProcessing, setForceFaceProcessing] = useState(false);
  const [showFaces, setShowFaces] = useState(false);
  const [selectedPersonByFaceId, setSelectedPersonByFaceId] = useState<Record<string, string>>({});
  const [selectedTagId, setSelectedTagId] = useState<string>("");
  const [prefetchedPreviewItems, setPrefetchedPreviewItems] = useState<Record<string, AssetPreviewEnsureItem>>({});
  const [prefetchedPreviewObjectUrls, setPrefetchedPreviewObjectUrls] = useState<Record<string, string>>({});
  const prefetchedPreviewUrlsRef = useRef<Set<string>>(new Set());
  const prefetchedObjectUrlsRef = useRef<Record<string, string>>({});
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["asset", assetId],
    queryFn: () => getAsset(assetId as string),
    enabled: Boolean(assetId),
  });
  const facesQuery = useQuery({
    queryKey: ["asset-faces", assetId],
    queryFn: () => getAssetFaces(assetId as string),
    enabled: Boolean(assetId) && showFaces,
  });
  const peopleQuery = useQuery({
    queryKey: ["people", "face-assignment-options"],
    queryFn: () => listPeople({ include_hidden: true }),
    enabled: Boolean(assetId) && showFaces,
  });
  const tagsQuery = useQuery({
    queryKey: ["tags", "asset-detail-options"],
    queryFn: listTags,
    enabled: Boolean(assetId),
  });

  const processFacesMutation = useMutation({
    mutationFn: () => triggerAssetFaceProcessing(assetId as string, forceFaceProcessing),
    onSuccess: async (job) => {
      pushToast(`Face job queued: ${job.id.slice(0, 8)}`, "success");
      setShowFaces(true);
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
      await facesQuery.refetch();
      await queryClient.invalidateQueries({ queryKey: ["asset", assetId] });
    },
    onError: (mutationError: Error) => pushToast(mutationError.message, "error"),
  });

  const updateFaceMutation = useMutation({
    mutationFn: ({
      faceId,
      payload,
    }: {
      faceId: string;
      payload: { person_id?: string | null; is_confirmed?: boolean; is_excluded?: boolean };
    }) => updateAssetFace(faceId, payload),
    onSuccess: async () => {
      pushToast("Face updated", "success");
      await queryClient.invalidateQueries({ queryKey: ["asset-faces", assetId] });
      await queryClient.invalidateQueries({ queryKey: ["people"] });
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
      await queryClient.invalidateQueries({ queryKey: ["search"] });
    },
    onError: (mutationError: Error) => pushToast(mutationError.message, "error"),
  });

  const updateThumbnailMutation = useMutation({
    mutationFn: ({ personId, assetId }: { personId: string; assetId: string }) =>
      updatePersonThumbnail(personId, assetId),
    onSuccess: async () => {
      pushToast("Person thumbnail updated", "success");
      await queryClient.invalidateQueries({ queryKey: ["person", thumbnailPersonId] });
      await queryClient.invalidateQueries({ queryKey: ["people"] });
    },
    onError: (mutationError: Error) => pushToast(mutationError.message, "error"),
  });

  const addTagMutation = useMutation({
    mutationFn: () => addAssetTag(assetId as string, Number(selectedTagId)),
    onSuccess: async () => {
      pushToast("Tag added", "success");
      setSelectedTagId("");
      await queryClient.invalidateQueries({ queryKey: ["asset", assetId] });
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
    onError: (mutationError: Error) => pushToast(mutationError.message, "error"),
  });

  const removeTagMutation = useMutation({
    mutationFn: (tagId: number) => removeAssetTag(assetId as string, tagId),
    onSuccess: async () => {
      pushToast("Tag removed", "success");
      await queryClient.invalidateQueries({ queryKey: ["asset", assetId] });
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
    onError: (mutationError: Error) => pushToast(mutationError.message, "error"),
  });

  useEffect(() => {
    setMounted(true);
    return () => {
      setMounted(false);
      for (const objectUrl of Object.values(prefetchedObjectUrlsRef.current)) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, []);

  useEffect(() => {
    setShowFaces(false);
    setForceFaceProcessing(false);
    setSelectedPersonByFaceId({});
    setSelectedTagId("");
  }, [assetId]);

  const people = peopleQuery.data ?? [];
  const faces = facesQuery.data ?? [];
  const tags = tagsQuery.data ?? [];

  useEffect(() => {
    if (!faces.length) {
      return;
    }
    setSelectedPersonByFaceId((current) => {
      const next = { ...current };
      for (const face of faces) {
        if (!(face.id in next)) {
          next[face.id] = face.person_id ?? "";
        }
      }
      return next;
    });
  }, [faces]);

  const sortedPeople = useMemo(
    () => people.slice().sort((a, b) => (a.asset_count - b.asset_count > 0 ? -1 : 1)),
    [people],
  );
  const sortedTags = useMemo(() => tags.slice().sort((a, b) => a.path.localeCompare(b.path)), [tags]);
  const currentAssetIndex = useMemo(
    () => navigationItems.findIndex((item) => item.id === assetId),
    [assetId, navigationItems],
  );
  const previousAsset = currentAssetIndex > 0 ? navigationItems[currentAssetIndex - 1] : null;
  const nextAsset =
    currentAssetIndex >= 0 && currentAssetIndex < navigationItems.length - 1
      ? navigationItems[currentAssetIndex + 1]
      : null;
  const neighboringAssets = useMemo(() => {
    if (currentAssetIndex < 0) {
      return [];
    }
    return navigationItems.filter((_, index) => Math.abs(index - currentAssetIndex) <= 2 && index !== currentAssetIndex);
  }, [currentAssetIndex, navigationItems]);
  const neighboringAssetIds = useMemo(
    () => neighboringAssets.map((item) => item.id),
    [neighboringAssets],
  );
  const readyPrefetchAssets = useMemo(
    () => neighboringAssets.filter((item) => prefetchedPreviewItems[item.id]?.status === "ready" && prefetchedPreviewItems[item.id]?.preview_url),
    [neighboringAssets, prefetchedPreviewItems],
  );
  const currentPrefetchedPreviewUrl = assetId ? prefetchedPreviewObjectUrls[assetId] ?? null : null;

  const handleEnsureResponse = useCallback((items: AssetPreviewEnsureItem[]) => {
    setPrefetchedPreviewItems((current) => mergePreviewItems(current, items));
  }, []);

  useEffect(() => {
    if (!assetId || neighboringAssetIds.length === 0) {
      return;
    }

    let cancelled = false;
    let timeoutId: number | null = null;

    const loadNeighbors = async () => {
      try {
        const response = await ensureAssetPreviews(neighboringAssetIds, "low");
        if (cancelled) {
          return;
        }
        setPrefetchedPreviewItems((current) => mergePreviewItems(current, response.items));

        const pendingNeighbors = response.items.some(
          (item) => item.status === "generating" || (item.status === "ready" && !item.preview_url),
        );
        if (pendingNeighbors) {
          timeoutId = window.setTimeout(() => {
            void loadNeighbors();
          }, 1500);
        }
      } catch {
        if (cancelled) {
          return;
        }
      }
    };

    void loadNeighbors();

    return () => {
      cancelled = true;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [assetId, neighboringAssetIds]);

  useEffect(() => {
    if (!assetId) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key === "ArrowLeft" && previousAsset && onSelectAsset) {
        event.preventDefault();
        onSelectAsset(previousAsset.id);
      }
      if (event.key === "ArrowRight" && nextAsset && onSelectAsset) {
        event.preventDefault();
        onSelectAsset(nextAsset.id);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [assetId, nextAsset, onClose, onSelectAsset, previousAsset]);

  useEffect(() => {
    if (readyPrefetchAssets.length === 0) {
      return;
    }

    const abortControllers: AbortController[] = [];

    for (const asset of readyPrefetchAssets) {
      const previewUrl = prefetchedPreviewItems[asset.id]?.preview_url;
      if (!previewUrl || prefetchedPreviewObjectUrls[asset.id] || prefetchedPreviewUrlsRef.current.has(previewUrl)) {
        continue;
      }

      prefetchedPreviewUrlsRef.current.add(previewUrl);
      const controller = new AbortController();
      abortControllers.push(controller);

      void (async () => {
        try {
          const response = await fetch(previewUrl, {
            signal: controller.signal,
            credentials: "same-origin",
            cache: "force-cache",
          });
          if (!response.ok) {
            throw new Error(`Failed to prefetch preview: ${response.status}`);
          }
          const blob = await response.blob();
          if (controller.signal.aborted) {
            return;
          }
          const objectUrl = URL.createObjectURL(blob);
          setPrefetchedPreviewObjectUrls((current) => {
            const previousObjectUrl = current[asset.id];
            if (previousObjectUrl) {
              URL.revokeObjectURL(previousObjectUrl);
            }
            const next = { ...current, [asset.id]: objectUrl };
            prefetchedObjectUrlsRef.current = next;
            return next;
          });
        } catch {
          if (controller.signal.aborted) {
            return;
          }
          prefetchedPreviewUrlsRef.current.delete(previewUrl);
        }
      })();
    }

    return () => {
      for (const controller of abortControllers) {
        controller.abort();
      }
    };
  }, [prefetchedPreviewItems, prefetchedPreviewObjectUrls, readyPrefetchAssets]);

  if (!assetId || !mounted) {
    return null;
  }

  const isVideo = Boolean(data?.mime_type?.startsWith("video/"));
  const isImage = Boolean(data && !isVideo);
  const fallbackThumbnailUrl = data?.small_thumbnail_url ?? null;

  return createPortal(
    <div
      className="fixed inset-0 z-[110] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex h-[85vh] w-full max-w-5xl flex-col overflow-hidden rounded-3xl border border-white/10 bg-ink-900 shadow-panel"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-white">Asset Metadata</h2>
            <p className="text-xs text-slate-400">{assetId}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => previousAsset && onSelectAsset?.(previousAsset.id)}
              disabled={!previousAsset || !onSelectAsset}
              className="rounded-full border border-white/10 p-2 text-slate-300 transition hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
              aria-label="Previous asset"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => nextAsset && onSelectAsset?.(nextAsset.id)}
              disabled={!nextAsset || !onSelectAsset}
              className="rounded-full border border-white/10 p-2 text-slate-300 transition hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
              aria-label="Next asset"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-white/10 p-2 text-slate-300 transition hover:bg-white/10 hover:text-white"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
        <div className="grid min-h-0 flex-1 gap-0 md:grid-cols-[1.1fr_0.9fr]">
          <div className="relative border-b border-white/10 bg-black/20 md:border-b-0 md:border-r">
            {data ? (
              isVideo ? (
                <AuthenticatedPreview
                  assetId={data.id}
                  previewUrl={data.preview_url}
                  prefetchedPreviewUrl={currentPrefetchedPreviewUrl}
                  mimeType={data.mime_type}
                  alt={data.master_path}
                  ensureAssetIds={neighboringAssetIds}
                  onEnsureResponse={handleEnsureResponse}
                  className="relative h-full w-full"
                  videoClassName="h-full w-full object-contain"
                  queuedMessage={
                    data.preview_status === "failed"
                      ? "Video preview previously failed. Retrying on demand."
                      : "Video preview is still being generated."
                  }
                />
              ) : (
                <div className="flex h-full items-center justify-center p-4">
                  <div className="relative inline-block max-h-full max-w-full">
                    <AuthenticatedPreview
                      assetId={data.id}
                      previewUrl={data.preview_url}
                      prefetchedPreviewUrl={currentPrefetchedPreviewUrl}
                      mimeType={data.mime_type}
                      alt={data.master_path}
                      fallbackUrl={fallbackThumbnailUrl}
                      ensureAssetIds={neighboringAssetIds}
                      onEnsureResponse={handleEnsureResponse}
                      className="relative"
                      imageClassName="block max-h-[calc(85vh-9rem)] max-w-full object-contain"
                    />
                    {showFaces && !facesQuery.isLoading ? (
                      <div className="pointer-events-none absolute inset-0">
                        {faces.map((face) => {
                          const style = faceBoxStyle(face);
                          if (!style) {
                            return null;
                          }
                          return (
                            <div
                              key={face.id}
                              className={`absolute border-2 ${
                                face.is_excluded
                                  ? "border-rose-400 bg-rose-400/10"
                                  : face.is_confirmed
                                    ? "border-emerald-400 bg-emerald-400/10"
                                    : "border-cyan-400 bg-cyan-400/10"
                              }`}
                              style={style}
                            />
                          );
                        })}
                      </div>
                    ) : null}
                  </div>
                </div>
              )
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-slate-500">
                {isLoading ? "Loading preview..." : "Preview unavailable"}
              </div>
            )}

            {readyPrefetchAssets.length > 0 ? (
              <div className="pointer-events-none absolute -left-[9999px] top-0 h-px w-px overflow-hidden opacity-0">
                {readyPrefetchAssets.map((asset) => {
                  const objectUrl = prefetchedPreviewObjectUrls[asset.id];
                  if (!objectUrl) {
                    return null;
                  }
                  return asset.mime_type.startsWith("video/") ? (
                    <video key={asset.id} src={objectUrl} preload="auto" muted playsInline className="h-px w-px" />
                  ) : (
                    <img key={asset.id} src={objectUrl} alt="" className="h-px w-px object-contain" />
                  );
                })}
              </div>
            ) : null}
          </div>
          <div className="scrollbar-thin overflow-y-auto px-5 py-4">
            {isLoading ? <p className="text-sm text-slate-400">Loading asset details...</p> : null}
            {isError ? <p className="text-sm text-rose-300">{(error as Error).message}</p> : null}
            {data ? (
              <div className="space-y-5">
                <section className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      onClick={() => processFacesMutation.mutate()}
                      disabled={!isImage || processFacesMutation.isPending}
                      className="flex items-center gap-2 rounded-2xl border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-sm text-cyan-200 transition hover:bg-cyan-400/20 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {processFacesMutation.isPending ? (
                        <LoaderCircle className="h-4 w-4 animate-spin" />
                      ) : (
                        <ScanFace className="h-4 w-4" />
                      )}
                      Detect faces
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowFaces((current) => !current)}
                      disabled={!isImage}
                      className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-2 text-sm text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {showFaces ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      {showFaces ? "Hide faces" : "Show faces"}
                    </button>
                    <label className="flex items-center gap-2 text-xs text-slate-300">
                      <input
                        type="checkbox"
                        checked={forceFaceProcessing}
                        onChange={(event) => setForceFaceProcessing(event.target.checked)}
                        className="h-4 w-4 rounded border-white/10 bg-black/20 text-cyan-400 focus:ring-cyan-400/40"
                      />
                      Force reprocess unconfirmed
                    </label>
                    {thumbnailPersonId && isImage ? (
                      <button
                        type="button"
                        onClick={() =>
                          updateThumbnailMutation.mutate({
                            personId: thumbnailPersonId,
                            assetId: assetId as string,
                          })
                        }
                        disabled={updateThumbnailMutation.isPending}
                        className="flex items-center gap-2 rounded-2xl border border-amber-400/30 bg-amber-400/10 px-4 py-2 text-sm text-amber-200 transition hover:bg-amber-400/20 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {updateThumbnailMutation.isPending ? (
                          <LoaderCircle className="h-4 w-4 animate-spin" />
                        ) : null}
                        Use image as thumbnail
                      </button>
                    ) : null}
                  </div>
                  {!isImage ? (
                    <p className="mt-3 text-xs text-slate-500">Face detection is only available for image assets.</p>
                  ) : null}
                  {processFacesMutation.data ? (
                    <a href={`/jobs/${processFacesMutation.data.id}`} className="mt-3 block text-xs text-cyan-300 underline">
                      Job {processFacesMutation.data.id}
                    </a>
                  ) : null}
                  {facesQuery.isLoading ? <p className="mt-3 text-xs text-slate-400">Loading faces...</p> : null}
                  {facesQuery.isError ? <p className="mt-3 text-xs text-rose-300">{(facesQuery.error as Error).message}</p> : null}
                  {showFaces && !facesQuery.isLoading && !facesQuery.isError && faces.length === 0 ? (
                    <p className="mt-3 text-xs text-slate-500">No faces detected for this asset yet.</p>
                  ) : null}
                </section>

                <section className="space-y-3 rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div>
                    <h3 className="text-sm font-semibold text-white">Tags</h3>
                    <p className="text-xs text-slate-400">Single-add/remove API. Parent tags are not materialized automatically.</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {data.tags.length > 0 ? data.tags.map((tag) => (
                      <button
                        key={tag.id}
                        type="button"
                        onClick={() => removeTagMutation.mutate(tag.id)}
                        disabled={removeTagMutation.isPending}
                        className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-200 transition hover:border-rose-400/40 hover:text-rose-200 disabled:opacity-60"
                        title="Click to remove explicit tag"
                      >
                        {tag.path} ×
                      </button>
                    )) : <p className="text-xs text-slate-500">No explicit tags.</p>}
                  </div>
                  <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_auto]">
                    <select
                      value={selectedTagId}
                      onChange={(event) => setSelectedTagId(event.target.value)}
                      className="min-w-0 rounded-2xl border border-white/10 bg-black/20 px-3 py-2 text-xs text-white outline-none focus:border-cyan-400/50"
                    >
                      <option value="">Select tag to add</option>
                      {sortedTags.map((tag) => (
                        <option key={tag.id} value={tag.id}>{tag.path}</option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={() => addTagMutation.mutate()}
                      disabled={!selectedTagId || addTagMutation.isPending}
                      className="rounded-2xl border border-cyan-400/30 bg-cyan-400/10 px-3 py-2 text-xs text-cyan-200 transition hover:bg-cyan-400/20 disabled:opacity-60"
                    >
                      Add tag
                    </button>
                  </div>
                </section>

                {showFaces && faces.length > 0 ? (
                  <section className="space-y-3 rounded-2xl border border-white/10 bg-black/20 p-4">
                    <div>
                      <h3 className="text-sm font-semibold text-white">Detected faces</h3>
                      <p className="text-xs text-slate-400">Bounding boxes are drawn from the oriented source image coordinates.</p>
                    </div>
                    <div className="space-y-3">
                      {faces.map((face, index) => (
                        <article key={face.id} className="rounded-2xl border border-white/10 bg-black/20 p-3 text-xs text-slate-200">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="rounded-full border border-white/10 px-2 py-1 text-[11px] text-white">Face {index + 1}</span>
                            <span className="rounded-full border border-white/10 px-2 py-1 text-[11px] text-slate-300">
                              Confidence {face.detection_confidence?.toFixed(3) ?? "n/a"}
                            </span>
                            {face.is_confirmed ? <span className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-1 text-[11px] text-emerald-200">Confirmed</span> : null}
                            {face.is_excluded ? <span className="rounded-full border border-rose-400/30 bg-rose-400/10 px-2 py-1 text-[11px] text-rose-200">Excluded</span> : null}
                          </div>

                          <div className="mt-3 grid gap-2 md:grid-cols-[minmax(0,1fr)_auto_auto_auto_auto]">
                            <select
                              value={selectedPersonByFaceId[face.id] ?? face.person_id ?? ""}
                              onChange={(event) =>
                                setSelectedPersonByFaceId((current) => ({
                                  ...current,
                                  [face.id]: event.target.value,
                                }))
                              }
                              className="min-w-0 rounded-2xl border border-white/10 bg-black/20 px-3 py-2 text-xs text-white outline-none focus:border-cyan-400/50"
                            >
                              <option value="">Unassigned</option>
                              {sortedPeople.map((person) => (
                                <option key={person.id} value={person.id}>
                                  {personLabel(person)}
                                </option>
                              ))}
                            </select>
                            <button
                              type="button"
                              onClick={() =>
                                updateFaceMutation.mutate({
                                  faceId: face.id,
                                  payload: {
                                    person_id: selectedPersonByFaceId[face.id] || null,
                                    is_excluded: false,
                                  },
                                })
                              }
                              disabled={updateFaceMutation.isPending}
                              className="rounded-2xl border border-cyan-400/30 bg-cyan-400/10 px-3 py-2 text-xs text-cyan-200 transition hover:bg-cyan-400/20 disabled:opacity-60"
                            >
                              Assign
                            </button>
                            <button
                              type="button"
                              onClick={() =>
                                updateFaceMutation.mutate({
                                  faceId: face.id,
                                  payload: { is_confirmed: true, is_excluded: false },
                                })
                              }
                              disabled={updateFaceMutation.isPending || face.is_confirmed}
                              className="rounded-2xl border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-xs text-emerald-200 transition hover:bg-emerald-400/20 disabled:opacity-60"
                            >
                              <span className="inline-flex items-center gap-1"><CheckCircle2 className="h-3.5 w-3.5" />Confirm</span>
                            </button>
                            <button
                              type="button"
                              onClick={() =>
                                updateFaceMutation.mutate({
                                  faceId: face.id,
                                  payload: {
                                    is_excluded: !face.is_excluded,
                                    person_id: !face.is_excluded ? null : face.person_id,
                                  },
                                })
                              }
                              disabled={updateFaceMutation.isPending}
                              className="rounded-2xl border border-rose-400/30 bg-rose-400/10 px-3 py-2 text-xs text-rose-200 transition hover:bg-rose-400/20 disabled:opacity-60"
                            >
                              {face.is_excluded ? "Unexclude" : "Exclude"}
                            </button>
                          </div>

                          <dl className="mt-3 space-y-1 text-slate-300">
                            <div>
                              <dt className="inline text-slate-500">Person ID:</dt>{" "}
                              <dd className="inline break-all">{face.person_id ?? "unassigned"}</dd>
                            </div>
                            <div>
                              <dt className="inline text-slate-500">Box:</dt>{" "}
                              <dd className="inline">
                                {face.bounding_box
                                  ? `${face.bounding_box.x}, ${face.bounding_box.y}, ${face.bounding_box.width} x ${face.bounding_box.height}`
                                  : "unavailable"}
                              </dd>
                            </div>
                            <div>
                              <dt className="inline text-slate-500">Crop:</dt>{" "}
                              <dd className="inline break-all">{face.crop_url ?? face.crop_path ?? "none"}</dd>
                            </div>
                            <div>
                              <dt className="inline text-slate-500">Updated:</dt>{" "}
                              <dd className="inline">{new Date(face.updated_at).toLocaleString()}</dd>
                            </div>
                          </dl>
                        </article>
                      ))}
                    </div>
                  </section>
                ) : null}

                <pre className="overflow-x-auto rounded-2xl border border-white/10 bg-black/20 p-4 text-xs leading-6 text-slate-200">
                  {JSON.stringify(data, null, 2)}
                </pre>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
