"use client";

import { LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { ensureAssetPreviews } from "@/lib/api/assets";
import type { AssetPreviewEnsureItem } from "@/lib/types";

type PreviewState = "idle" | "loading" | "ready" | "generating" | "error";

type AuthenticatedPreviewProps = {
  assetId: string;
  previewUrl: string | null | undefined;
  prefetchedPreviewUrl?: string | null;
  mimeType: string;
  alt: string;
  fallbackUrl?: string | null;
  ensureAssetIds?: string[];
  onEnsureResponse?: (items: AssetPreviewEnsureItem[]) => void;
  className?: string;
  imageClassName?: string;
  videoClassName?: string;
  queuedMessage?: string;
  errorMessage?: string;
};

function resultMessage(item: AssetPreviewEnsureItem | null, fallback: string) {
  if (!item) {
    return fallback;
  }
  if (item.error) {
    return item.error;
  }
  switch (item.status) {
    case "generating":
      return "Preview is still being generated.";
    case "unsupported":
      return "Preview is not supported for this asset.";
    case "not_found":
      return "Asset preview is not accessible.";
    case "failed":
      return "Preview generation failed.";
    default:
      return fallback;
  }
}

export function AuthenticatedPreview({
  assetId,
  previewUrl,
  prefetchedPreviewUrl,
  mimeType,
  alt,
  fallbackUrl,
  ensureAssetIds,
  onEnsureResponse,
  className,
  imageClassName,
  videoClassName,
  queuedMessage = "Preview is still being generated.",
  errorMessage = "Preview unavailable.",
}: AuthenticatedPreviewProps) {
  const [resolvedPreviewUrl, setResolvedPreviewUrl] = useState<string | null>(
    prefetchedPreviewUrl ?? previewUrl ?? null,
  );
  const [state, setState] = useState<PreviewState>("idle");
  const [message, setMessage] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    let timeoutId: number | null = null;

    const load = async () => {
      setState(prefetchedPreviewUrl ? "ready" : "loading");
      setMessage("");
      try {
        const requestedAssetIds = Array.from(
          new Set([assetId, ...(ensureAssetIds ?? [])]),
        );
        const response = await ensureAssetPreviews(requestedAssetIds, "low");
        if (cancelled) {
          return;
        }
        onEnsureResponse?.(response.items);
        const item = response.items.find((entry) => entry.asset_id === assetId) ?? null;
        if (!item) {
          setState("error");
          setMessage(errorMessage);
          return;
        }
        if (item.status === "ready" && item.preview_url) {
          setResolvedPreviewUrl(prefetchedPreviewUrl ?? item.preview_url);
          setState("ready");
          return;
        }
        if (item.status === "generating") {
          setResolvedPreviewUrl(prefetchedPreviewUrl ?? previewUrl ?? null);
          if (!prefetchedPreviewUrl) {
            setState("generating");
            setMessage(queuedMessage);
          }
          timeoutId = window.setTimeout(() => {
            void load();
          }, 3000);
          return;
        }
        setState("error");
        setMessage(resultMessage(item, errorMessage));
      } catch (error) {
        if (cancelled) {
          return;
        }
        setState("error");
        setMessage(error instanceof Error ? error.message : errorMessage);
      }
    };

    setResolvedPreviewUrl(prefetchedPreviewUrl ?? previewUrl ?? null);
    void load();

    return () => {
      cancelled = true;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [assetId, ensureAssetIds, errorMessage, onEnsureResponse, prefetchedPreviewUrl, previewUrl, queuedMessage]);

  const isVideo = mimeType.startsWith("video/");

  if (state === "ready" && resolvedPreviewUrl) {
    return isVideo ? (
      <video
        src={resolvedPreviewUrl}
        controls
        preload="metadata"
        className={videoClassName}
      />
    ) : (
      <img src={resolvedPreviewUrl} alt={alt} className={imageClassName} />
    );
  }

  if ((state === "loading" || state === "generating") && fallbackUrl && !isVideo) {
    return (
      <div className={className}>
        <img src={fallbackUrl} alt={alt} className={imageClassName} />
        <div className="pointer-events-none absolute inset-x-4 bottom-4 rounded-2xl border border-white/10 bg-black/60 px-3 py-2 text-xs text-slate-200 backdrop-blur">
          <span className="inline-flex items-center gap-2">
            <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
            {message || queuedMessage}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full items-center justify-center px-6 text-center text-sm text-slate-400">
      {state === "loading" ? (
        <span className="inline-flex items-center gap-2">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Loading preview...
        </span>
      ) : (
        message || errorMessage
      )}
    </div>
  );
}
