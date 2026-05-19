"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, LoaderCircle, ScanFace, X } from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { useToast } from "@/components/toast-provider";
import { getAsset } from "@/lib/api/assets";
import { getAssetFaces, triggerAssetFaceProcessing } from "@/lib/api/faces";
import type { AssetFace } from "@/lib/types";

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

export function AssetDetailModal({ assetId, onClose }: AssetDetailModalProps) {
  const [mounted, setMounted] = useState(false);
  const [forceFaceProcessing, setForceFaceProcessing] = useState(false);
  const [showFaces, setShowFaces] = useState(false);
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

  useEffect(() => {
    setMounted(true);
    return () => setMounted(false);
  }, []);

  useEffect(() => {
    setShowFaces(false);
    setForceFaceProcessing(false);
  }, [assetId]);

  if (!assetId || !mounted) {
    return null;
  }

  const isVideo = Boolean(data?.mime_type?.startsWith("video/"));
  const isImage = Boolean(data && !isVideo);
  const isVideoPreviewReady = data?.preview_status === "ready";
  const faces = facesQuery.data ?? [];

  return createPortal(
    <div
      className="fixed inset-0 z-[110] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex h-[85vh] w-full max-w-4xl flex-col overflow-hidden rounded-3xl border border-white/10 bg-ink-900 shadow-panel"
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
                  {facesQuery.isLoading ? (
                    <p className="mt-3 text-xs text-slate-400">Loading faces...</p>
                  ) : null}
                  {facesQuery.isError ? (
                    <p className="mt-3 text-xs text-rose-300">{(facesQuery.error as Error).message}</p>
                  ) : null}
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
                              <dt className="inline text-slate-500">Created:</dt>{" "}
                              <dd className="inline">{new Date(face.created_at).toLocaleString()}</dd>
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
