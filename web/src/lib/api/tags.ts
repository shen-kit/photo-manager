import { apiRequest } from "@/lib/api/client";
import type { AssetGridPage, Tag, TagCreatePayload, TagUpdatePayload } from "@/lib/types";

export function listTags() {
  return apiRequest<Tag[]>("/api/v1/tags/", { auth: true });
}

export function createTag(payload: TagCreatePayload) {
  return apiRequest<Tag>("/api/v1/tags/", {
    method: "POST",
    body: JSON.stringify(payload),
    auth: true,
  });
}

export function updateTag(tagId: number, payload: TagUpdatePayload) {
  return apiRequest<Tag>(`/api/v1/tags/${tagId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
    auth: true,
  });
}

export function deleteTag(tagId: number, deleteChildren = false) {
  const search = new URLSearchParams({ delete_children: String(deleteChildren) });
  return apiRequest<void>(`/api/v1/tags/${tagId}?${search.toString()}`, {
    method: "DELETE",
    auth: true,
    contentType: null,
  });
}

export function listTagAssets(tagId: number, cursor?: string | null) {
  const search = new URLSearchParams({ limit: "24" });
  if (cursor) {
    search.set("cursor", cursor);
  }
  return apiRequest<AssetGridPage>(`/api/v1/tags/${tagId}/assets?${search.toString()}`, {
    auth: true,
  });
}
