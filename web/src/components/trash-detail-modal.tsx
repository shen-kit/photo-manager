"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, LoaderCircle, RotateCcw, X } from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { AuthenticatedPreview } from "@/components/authenticated-preview";
import { useToast } from "@/components/toast-provider";
import { getTrashAsset, restoreTrashAsset } from "@/lib/api/trash";
import { formatDateTime, formatJson } from "@/lib/format";

type TrashDetailModalProps = {
  assetId: string | null;
  onClose: () => void;
};

export function TrashDetailModal({ assetId, onClose }: TrashDetailModalProps) {
  const [mounted, setMounted] = useState(false);
  const queryClient = useQueryClient();
  const { pushToast } = useToast();

  useEffect(() => {
    setMounted(true);
    return () => setMounted(false);
  }, []);

  const detailQuery = useQuery({
    queryKey: ["trash-asset", assetId],
    queryFn: () => getTrashAsset(assetId as string),
    enabled: Boolean(assetId),
  });

  const restoreMutation = useMutation({
    mutationFn: () => restoreTrashAsset(assetId as string),
    onSuccess: async () => {
      pushToast("Asset restored", "success");
      await queryClient.invalidateQueries({ queryKey: ["trash-assets"] });
      await queryClient.invalidateQueries({ queryKey: ["assets"] });
      await queryClient.invalidateQueries({ queryKey: ["search"] });
      onClose();
    },
    onError: (error: Error) => pushToast(error.message, "error"),
  });

  if (!assetId || !mounted) {
    return null;
  }

  const asset = detailQuery.data;
  const isVideo = asset?.mime_type?.startsWith("video/");
  const fallbackThumbnailUrl = asset
    ? `/media/processed/assets/${asset.id}/small.webp`
    : null;

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
            <h2 className="text-lg font-semibold text-white">Trash Asset</h2>
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
            {detailQuery.isLoading ? (
              <div className="flex h-full items-center justify-center text-sm text-slate-400">
                <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
                Loading preview...
              </div>
            ) : detailQuery.isError ? (
              <div className="flex h-full items-center justify-center px-6 text-center text-sm text-rose-300">
                {(detailQuery.error as Error).message}
              </div>
            ) : asset ? (
              isVideo ? (
                <AuthenticatedPreview
                  assetId={asset.id}
                  previewUrl={asset.preview_url}
                  mimeType={asset.mime_type}
                  alt={asset.master_path}
                  className="relative h-full w-full"
                  videoClassName="h-full w-full object-contain"
                  queuedMessage="Preview request queued. Deleted-asset previews may depend on backend support."
                  errorMessage="Preview unavailable for this trashed asset."
                />
              ) : (
                <div className="flex h-full items-center justify-center p-4">
                  <AuthenticatedPreview
                    assetId={asset.id}
                    previewUrl={asset.preview_url}
                    mimeType={asset.mime_type}
                    alt={asset.master_path}
                    fallbackUrl={fallbackThumbnailUrl}
                    className="relative"
                    imageClassName="block max-h-[calc(85vh-9rem)] max-w-full object-contain"
                    queuedMessage="Preview request queued. Deleted-asset previews may depend on backend support."
                    errorMessage="Preview unavailable for this trashed asset."
                  />
                </div>
              )
            ) : null}
          </div>
          <div className="scrollbar-thin overflow-y-auto px-5 py-4">
            {asset ? (
              <div className="space-y-5">
                <section className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      onClick={() => restoreMutation.mutate()}
                      disabled={restoreMutation.isPending}
                      className="flex items-center gap-2 rounded-2xl border border-emerald-400/30 bg-emerald-400/10 px-4 py-2 text-sm text-emerald-200 transition hover:bg-emerald-400/20 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {restoreMutation.isPending ? (
                        <LoaderCircle className="h-4 w-4 animate-spin" />
                      ) : (
                        <RotateCcw className="h-4 w-4" />
                      )}
                      Restore asset
                    </button>
                    <div className="flex items-center gap-2 text-xs text-amber-200">
                      <AlertCircle className="h-4 w-4" />
                      Deleted {formatDateTime(asset.deleted_at)}
                    </div>
                  </div>
                </section>

                <section className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <h3 className="text-sm font-semibold text-white">Metadata</h3>
                  <dl className="mt-3 grid grid-cols-[120px_1fr] gap-x-3 gap-y-2 text-sm">
                    <dt className="text-slate-500">Path</dt>
                    <dd className="break-all text-slate-200">{asset.master_path}</dd>
                    <dt className="text-slate-500">Type</dt>
                    <dd className="text-slate-200">{asset.mime_type}</dd>
                    <dt className="text-slate-500">Captured</dt>
                    <dd className="text-slate-200">{formatDateTime(asset.captured_at)}</dd>
                    <dt className="text-slate-500">Created</dt>
                    <dd className="text-slate-200">{formatDateTime(asset.created_at)}</dd>
                    <dt className="text-slate-500">Faces</dt>
                    <dd className="text-slate-200">{asset.faces.length}</dd>
                    <dt className="text-slate-500">People</dt>
                    <dd className="text-slate-200">{asset.people.length}</dd>
                    <dt className="text-slate-500">Description</dt>
                    <dd className="text-slate-200">{asset.description || "—"}</dd>
                  </dl>
                </section>

                <section className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <h3 className="text-sm font-semibold text-white">EXIF</h3>
                  <pre className="mt-3 max-h-48 overflow-auto rounded-2xl bg-black/30 p-3 text-xs text-slate-300">
                    {formatJson(asset.exif_data)}
                  </pre>
                </section>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
