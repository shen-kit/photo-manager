"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Eye, EyeOff, LoaderCircle, ScanFace, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

import { useToast } from "@/components/toast-provider";
import { getAsset } from "@/lib/api/assets";
import { getAssetFaces, triggerAssetFaceProcessing, updateAssetFace } from "@/lib/api/faces";
import { listPeople } from "@/lib/api/people";
import type { AssetFace, Person } from "@/lib/types";

type AssetDetailModalProps = {
  assetId: string | null;
  onClose: () => void;
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

export function AssetDetailModal({ assetId, onClose }: AssetDetailModalProps) {
  const [mounted, setMounted] = useState(false);
  const [forceFaceProcessing, setForceFaceProcessing] = useState(false);
  const [showFaces, setShowFaces] = useState(false);
  const [selectedPersonByFaceId, setSelectedPersonByFaceId] = useState<Record<string, string>>( {} );
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

  const processFacesMutation = useMutation({
    mutationFn: () => triggerAssetFaceProcessing(assetId as string, forceFaceProcessing),
    onSuccess: async (job) => {
      pushToast(`Face job queued: ${job.id.slice(0, 8)}`, "success");
      setShowFaces(true);
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
      await facesQuery.refetch();
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
      await queryClient.invalidateQueries({ queryKey: ["person-assets"] });
      await queryClient.invalidateQueries({ queryKey: ["search"] });
    },
    onError: (mutationError: Error) => pushToast(mutationError.message, "error"),
  });

  useEffect(() => {
    setMounted(true);
    return () => setMounted(false);
  }, []);

  useEffect(() => {
    setShowFaces(false);
    setForceFaceProcessing(false);
    setSelectedPersonByFaceId({});
  }, [assetId]);

  const people = peopleQuery.data ?? [];
  const faces = facesQuery.data ?? [];

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

  const sortedPeople = useMemo(() => people.slice().sort((a, b) => a.asset_count - b.asset_count > 0 ? -1 : 1), [people]);

  if (!assetId || !mounted) {
    return null;
  }

  const isVideo = Boolean(data?.mime_type?.startsWith("video/"));
  const isImage = Boolean(data && !isVideo);
  const isVideoPreviewReady = data?.preview_status === "ready";

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
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-white/10 p-2 text-slate-300 transition hover:bg-white/10 hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="grid min-h-0 flex-1 gap-0 md:grid-cols-[1.1fr_0.9fr]">
          <div className="border-b border-white/10 bg-black/20 md:border-b-0 md:border-r">
            {data ? (
              isVideo ? (
                isVideoPreviewReady ? (
                  <video
                    src={data.large_preview_url}
                    controls
                    preload="metadata"
                    className="h-full w-full object-contain"
                  />
                ) : (
                  <div className="flex h-full items-center justify-center px-6 text-center text-sm text-slate-400">
                    {data?.preview_status === "failed"
                      ? "Video preview generation failed. Check the asset metadata for codec details."
                      : "Video preview is still being generated."}
                  </div>
                )
              ) : (
                <div className="flex h-full items-center justify-center p-4">
                  <div className="relative inline-block max-h-full max-w-full">
                    <img
                      src={data.large_preview_url}
                      alt={data.master_path}
                      className="block max-h-[calc(85vh-9rem)] max-w-full object-contain"
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

                          <div className="mt-3 grid gap-2 md:grid-cols-[minmax(0,1fr)_auto_auto_auto]">
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
