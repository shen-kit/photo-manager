import { apiRequest } from "@/lib/api/client";
import type {
  Job,
  ManualJobCatalog,
  ManualJobRunPayload,
  ManualJobRunResponse,
} from "@/lib/types";

export function getJobs() {
  return apiRequest<Job[]>("/api/v1/jobs", {
    auth: true,
  });
}

export function getJob(jobId: string) {
  return apiRequest<Job>(`/api/v1/jobs/${jobId}`, {
    auth: true,
  });
}

export function getAvailableJobs() {
  return apiRequest<ManualJobCatalog>("/api/v1/jobs/available", {
    auth: true,
  });
}

export function runManualJob(jobKey: string, payload?: ManualJobRunPayload) {
  return apiRequest<ManualJobRunResponse>(`/api/v1/jobs/${jobKey}/run`, {
    method: "POST",
    auth: true,
    body: payload ? JSON.stringify(payload) : null,
  });
}
