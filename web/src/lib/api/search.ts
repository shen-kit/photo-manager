import { apiRequest } from "@/lib/api/client";
import { runManualJob } from "@/lib/api/jobs";
import type { SearchResponse } from "@/lib/types";

export function searchAssets(query: string, limit = 24, offset = 0, personIds: string[] = []) {
  const search = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (query.trim()) {
    search.set("query", query.trim());
  }
  if (personIds.length > 0) {
    search.set("person_ids", personIds.join(","));
  }
  return apiRequest<SearchResponse>(`/api/v1/search?${search.toString()}`, {
    auth: true,
  });
}

export function triggerClipBackfill(force = false) {
  return runManualJob("run_missing_or_outdated_clip_embeddings", {
    params: { force },
  }).then((response) => response.job);
}
