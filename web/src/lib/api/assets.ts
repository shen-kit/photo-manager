import { apiRequest } from "@/lib/api/client";
import { runManualJob } from "@/lib/api/jobs";
import type {
  AssetDetail,
  AssetGridPage,
  AssetIngestResponse,
  AssetPreviewEnsureResponse,
  AssetUpdatePayload,
} from "@/lib/types";

type ListAssetsParams = {
  limit?: number;
  cursor?: string | null;
  mediaKind?: "image" | "video";
  month?: string;
  day?: string;
  personIds?: string[];
  tagIds?: number[];
};

export function listAssets(params: ListAssetsParams = {}) {
  const search = new URLSearchParams();
  search.set("limit", String(params.limit ?? 24));
  if (params.cursor) {
    search.set("cursor", params.cursor);
  }
  if (params.mediaKind) {
    search.set("media_kind", params.mediaKind);
  }
  if (params.month) {
    search.set("month", params.month);
  }
  if (params.day) {
    search.set("day", params.day);
  }
  if (params.personIds?.length) {
    search.set("person_ids", params.personIds.join(","));
  }
  if (params.tagIds?.length) {
    search.set("tag_ids", params.tagIds.join(","));
  }
  return apiRequest<AssetGridPage>(`/api/v1/assets?${search.toString()}`, {
    auth: true,
  });
}

export function getAsset(assetId: string) {
  return apiRequest<AssetDetail>(`/api/v1/assets/${assetId}`, {
    auth: true,
  });
}

export function ensureAssetPreviews(
  assetIds: string[],
  priority: "low" | "normal" | "high" = "low",
) {
  return apiRequest<AssetPreviewEnsureResponse>("/api/v1/assets/previews/ensure", {
    method: "POST",
    body: JSON.stringify({
      asset_ids: assetIds,
      priority,
    }),
    auth: true,
  });
}

export function uploadAsset(file: File) {
  const formData = new FormData();
  formData.append("file", file);

  return apiRequest<AssetIngestResponse>("/api/v1/assets/upload", {
    method: "POST",
    body: formData,
    auth: true,
    contentType: null,
  });
}

export function ingestPath(filePath: string) {
  return apiRequest<AssetIngestResponse>("/api/v1/assets/ingest", {
    method: "POST",
    body: JSON.stringify({ file_path: filePath }),
    auth: true,
  });
}

export function scanAssets() {
  return runManualJob("bulk_scan").then((response) => response.job);
}

export function updateAsset(assetId: string, payload: AssetUpdatePayload) {
  return apiRequest<AssetDetail>(`/api/v1/assets/${assetId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
    auth: true,
  });
}

export function deleteAsset(assetId: string) {
  return apiRequest<void>(`/api/v1/assets/${assetId}`, {
    method: "DELETE",
    auth: true,
    contentType: null,
  });
}

export function addAssetTag(assetId: string, tagId: number) {
  return apiRequest<void>(`/api/v1/assets/${assetId}/tags/${tagId}`, {
    method: "POST",
    auth: true,
    contentType: null,
  });
}

export function removeAssetTag(assetId: string, tagId: number) {
  return apiRequest<void>(`/api/v1/assets/${assetId}/tags/${tagId}`, {
    method: "DELETE",
    auth: true,
    contentType: null,
  });
}

export function batchAddAssetTags(assetIds: string[], tagIds: number[]) {
  return apiRequest<{ updated_count: number }>("/api/v1/assets/tags:batch-add", {
    method: "POST",
    body: JSON.stringify({ asset_ids: assetIds, tag_ids: tagIds }),
    auth: true,
  });
}

export function batchRemoveAssetTags(assetIds: string[], tagIds: number[]) {
  return apiRequest<{ updated_count: number }>("/api/v1/assets/tags:batch-remove", {
    method: "POST",
    body: JSON.stringify({ asset_ids: assetIds, tag_ids: tagIds }),
    auth: true,
  });
}
