import { apiRequest } from "@/lib/api/client";
import type {
  AssetListResponse,
  Job,
  Person,
  PersonListParams,
  PersonMergeResponse,
  PersonUpdatePayload,
} from "@/lib/types";

export function triggerPeopleClustering(payload: {
  threshold?: number;
  top_k?: number;
  min_cluster_size?: number;
}) {
  return apiRequest<Job>("/api/v1/people/cluster", {
    method: "POST",
    body: JSON.stringify(payload),
    auth: true,
  });
}

export function listPeople(params: PersonListParams = {}) {
  const search = new URLSearchParams();
  if (params.include_hidden) {
    search.set("include_hidden", "true");
  }
  if (params.search?.trim()) {
    search.set("search", params.search.trim());
  }
  const suffix = search.toString();
  return apiRequest<Person[]>(`/api/v1/people${suffix ? `?${suffix}` : ""}`, {
    auth: true,
  });
}

export function getPerson(personId: string) {
  return apiRequest<Person>(`/api/v1/people/${personId}`, {
    auth: true,
  });
}

export function updatePerson(personId: string, payload: PersonUpdatePayload) {
  return apiRequest<Person>(`/api/v1/people/${personId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
    auth: true,
  });
}

export function updatePersonThumbnail(personId: string, assetId: string) {
  return apiRequest<Person>(`/api/v1/people/${personId}/thumbnail`, {
    method: "PATCH",
    body: JSON.stringify({ asset_id: assetId }),
    auth: true,
  });
}

export function getPersonAssets(personId: string, page = 1, pageSize = 24) {
  const search = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  return apiRequest<AssetListResponse>(
    `/api/v1/people/${personId}/assets?${search.toString()}`,
    { auth: true },
  );
}

export function mergePeople(sourcePersonId: string, targetPersonId: string) {
  return apiRequest<PersonMergeResponse>(
    `/api/v1/people/${sourcePersonId}/merge-into/${targetPersonId}`,
    {
      method: "POST",
      auth: true,
      contentType: null,
    },
  );
}
