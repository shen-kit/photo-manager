import { apiRequest } from "@/lib/api/client";
import type {
  DiagnosticDefinitionList,
  DiagnosticRunDetail,
  DiagnosticRunItemPage,
  DiagnosticRunList,
  DiagnosticRunResponse,
} from "@/lib/types";

export function listDiagnostics() {
  return apiRequest<DiagnosticDefinitionList>("/api/v1/system/integrity/diagnostics", {
    auth: true,
  });
}

export function runDiagnostic(diagnosticKey: string) {
  return apiRequest<DiagnosticRunResponse>(
    `/api/v1/system/integrity/diagnostics/${diagnosticKey}/run`,
    {
      method: "POST",
      auth: true,
      contentType: null,
    },
  );
}

export function listDiagnosticRuns(diagnosticKey?: string | null) {
  const search = new URLSearchParams({ limit: "50", offset: "0" });
  if (diagnosticKey) {
    search.set("diagnostic_key", diagnosticKey);
  }
  return apiRequest<DiagnosticRunList>(`/api/v1/system/integrity/runs?${search.toString()}`, {
    auth: true,
  });
}

export function getDiagnosticRun(runId: string) {
  return apiRequest<DiagnosticRunDetail>(`/api/v1/system/integrity/runs/${runId}`, {
    auth: true,
  });
}

export function listDiagnosticRunItems(runId: string, offset = 0, limit = 100) {
  const search = new URLSearchParams({ offset: String(offset), limit: String(limit) });
  return apiRequest<DiagnosticRunItemPage>(
    `/api/v1/system/integrity/runs/${runId}/items?${search.toString()}`,
    { auth: true },
  );
}

export function repairDiagnosticRun(runId: string) {
  return apiRequest<DiagnosticRunResponse>(`/api/v1/system/integrity/runs/${runId}/repair`, {
    method: "POST",
    auth: true,
    contentType: null,
  });
}
