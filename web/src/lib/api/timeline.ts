import { apiRequest } from "@/lib/api/client";
import type { TimelineDayBucket, TimelineMonthBucket } from "@/lib/types";

type TimelineFilterParams = {
  mediaKind?: "image" | "video";
  personIds?: string[];
};

function buildSearch(params: TimelineFilterParams & { month?: string }) {
  const search = new URLSearchParams();
  if (params.mediaKind) {
    search.set("media_kind", params.mediaKind);
  }
  if (params.personIds?.length) {
    search.set("person_ids", params.personIds.join(","));
  }
  if (params.month) {
    search.set("month", params.month);
  }
  return search.toString();
}

export function listTimelineMonths(params: TimelineFilterParams = {}) {
  const search = buildSearch(params);
  return apiRequest<TimelineMonthBucket[]>(
    `/api/v1/timeline/months${search ? `?${search}` : ""}`,
    { auth: true },
  );
}

export function listTimelineDays(month: string, params: TimelineFilterParams = {}) {
  const search = buildSearch({ ...params, month });
  return apiRequest<TimelineDayBucket[]>(
    `/api/v1/timeline/days${search ? `?${search}` : ""}`,
    { auth: true },
  );
}
