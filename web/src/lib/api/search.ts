import { apiRequest } from "@/lib/api/client";
import type { Job, SearchResponse } from "@/lib/types";

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
  const search = new URLSearchParams({ force: String(force) });
  return apiRequest<Job>(`/api/v1/search/backfill?${search.toString()}`, {
    method: "POST",
    auth: true,
    contentType: null,
  });
}
