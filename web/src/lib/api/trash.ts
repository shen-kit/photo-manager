import { apiRequest } from "@/lib/api/client";
import type {
  TrashAssetDetail,
  TrashAssetListResponse,
  TrashBulkDeletePayload,
  TrashBulkRestorePayload,
  TrashBulkRestoreResponse,
  TrashDeleteSummaryResponse,
  TrashEmptyResponse,
  TrashRestoreResponse,
  TrashSort,
} from "@/lib/types";

export function listTrashAssets(page: number, pageSize: number, sort: TrashSort) {
  const search = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    sort,
  });
  return apiRequest<TrashAssetListResponse>(`/api/v1/trash/assets?${search.toString()}`, {
    auth: true,
  });
}

export function getTrashAsset(assetId: string) {
  return apiRequest<TrashAssetDetail>(`/api/v1/trash/assets/${assetId}`, {
    auth: true,
  });
}

export function restoreTrashAsset(assetId: string) {
  return apiRequest<TrashRestoreResponse>(`/api/v1/trash/assets/${assetId}/restore`, {
    method: "POST",
    auth: true,
    contentType: null,
  });
}

export function restoreTrashAssets(payload: TrashBulkRestorePayload) {
  return apiRequest<TrashBulkRestoreResponse>("/api/v1/trash/assets/restore", {
    method: "POST",
    auth: true,
    body: JSON.stringify(payload),
  });
}

export function permanentlyDeleteTrashAsset(assetId: string) {
  return apiRequest<void>(`/api/v1/trash/assets/${assetId}`, {
    method: "DELETE",
    auth: true,
    contentType: null,
  });
}

export function permanentlyDeleteTrashAssets(payload: TrashBulkDeletePayload) {
  return apiRequest<TrashDeleteSummaryResponse>("/api/v1/trash/assets/delete", {
    method: "POST",
    auth: true,
    body: JSON.stringify(payload),
  });
}

export function emptyTrash() {
  return apiRequest<TrashEmptyResponse>("/api/v1/trash/assets/", {
    method: "DELETE",
    auth: true,
    contentType: null,
  });
}
