import { apiRequest } from "@/lib/api/client";
import type { Job } from "@/lib/types";

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
