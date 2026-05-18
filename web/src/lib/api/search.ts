import { apiRequest } from "@/lib/api/client";
import type { Job, SearchResponse } from "@/lib/types";

export function searchAssets(query: string, limit = 24, offset = 0) {
  const search = new URLSearchParams({
    query,
    limit: String(limit),
    offset: String(offset),
  });
  return apiRequest<SearchResponse>(`/api/v1/search?${search.toString()}`, {
    auth: true,
  });
}

export function triggerClipBackfill(force = false) {
  const search = new URLSearchParams({ force: String(force) });
  return apiRequest<Job>(`/api/v1/search/backfill?${search.toString()}`, {
    method: "POST",
    auth: true,
    contentType: null,
  });
}
