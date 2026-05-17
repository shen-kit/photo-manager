"use client";

import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { getAsset } from "@/lib/api/assets";

type AssetDetailModalProps = {
  assetId: string | null;
  onClose: () => void;
};

export function AssetDetailModal({ assetId, onClose }: AssetDetailModalProps) {
  const [mounted, setMounted] = useState(false);
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["asset", assetId],
    queryFn: () => getAsset(assetId as string),
    enabled: Boolean(assetId),
  });

  useEffect(() => {
    setMounted(true);
    return () => setMounted(false);
  }, []);

  if (!assetId || !mounted) {
    return null;
  }

  const isVideo = Boolean(data?.mime_type?.startsWith("video/"));
  const isVideoPreviewReady = data?.preview_status === "ready";

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
                <img src={data.large_preview_url} alt={data.master_path} className="h-full w-full object-contain" />
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
              <pre className="text-xs leading-6 text-slate-200">{JSON.stringify(data, null, 2)}</pre>
            ) : null}
          </div>
        </div>
      </div>
    </div>
    ,
    document.body,
  );
}
