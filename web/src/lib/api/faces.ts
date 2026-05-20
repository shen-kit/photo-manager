import { apiRequest } from "@/lib/api/client";
import { runManualJob } from "@/lib/api/jobs";
import type { AssetFace, Job } from "@/lib/types";

export function triggerFaceBackfill(force = false) {
  return runManualJob("run_missing_or_outdated_face_recognition", {
    params: {
      force,
      auto_match: false,
    },
  }).then((response) => response.job);
}

export function triggerAssetFaceProcessing(assetId: string, force = false) {
  const search = new URLSearchParams({ force: String(force) });
  return apiRequest<Job>(`/api/v1/assets/${assetId}/faces/process?${search.toString()}`, {
    method: "POST",
    auth: true,
    contentType: null,
  });
}

export function getAssetFaces(assetId: string) {
  return apiRequest<AssetFace[]>(`/api/v1/assets/${assetId}/faces`, {
    auth: true,
  });
}


export function updateAssetFace(faceId: string, payload: {
  person_id?: string | null;
  is_confirmed?: boolean;
  is_excluded?: boolean;
}) {
  return apiRequest<AssetFace>(`/api/v1/faces/${faceId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
    auth: true,
  });
}
