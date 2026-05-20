import { apiRequest } from "@/lib/api/client";
import { runManualJob } from "@/lib/api/jobs";
import type {
  AssetDetail,
  AssetIngestResponse,
  AssetListResponse,
  AssetUpdatePayload,
} from "@/lib/types";

export function listAssets(page: number, pageSize: number) {
  const search = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  return apiRequest<AssetListResponse>(`/api/v1/assets?${search.toString()}`, {
    auth: true,
  });
}

export function getAsset(assetId: string) {
  return apiRequest<AssetDetail>(`/api/v1/assets/${assetId}`, {
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
