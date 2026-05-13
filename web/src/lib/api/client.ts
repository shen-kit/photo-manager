import { clearSession, loadSession, saveSession } from "@/lib/auth-store";
import type { AuthResponse } from "@/lib/types";

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: BodyInit | string | null;
  headers?: HeadersInit;
  auth?: boolean;
  contentType?: string | null;
};

let refreshPromise: Promise<string | null> | null = null;

function buildHeaders(options: RequestOptions) {
  const headers = new Headers(options.headers);
  if (options.contentType !== null && !headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", options.contentType ?? "application/json");
  }

  if (options.auth) {
    const session = loadSession();
    if (session?.accessToken) {
      headers.set("Authorization", `Bearer ${session.accessToken}`);
    }
  }

  return headers;
}

async function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const response = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        credentials: "include",
      });

      if (!response.ok) {
        clearSession();
        return null;
      }

      const payload = (await response.json()) as AuthResponse;
      const expiresAt = Date.now() + payload.expires_in * 1000;
      saveSession({
        accessToken: payload.access_token,
        expiresAt,
        user: payload.user,
      });
      return payload.access_token;
    })().finally(() => {
      refreshPromise = null;
    });
  }

  return refreshPromise;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const execute = async () =>
    fetch(path, {
      method: options.method ?? "GET",
      body: options.body ?? null,
      headers: buildHeaders(options),
      credentials: "include",
    });

  let response = await execute();

  if (response.status === 401 && options.auth) {
    const accessToken = await refreshAccessToken();
    if (accessToken) {
      response = await execute();
    }
  }

  if (!response.ok) {
    let detail = "Request failed";
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      detail = response.statusText || detail;
    }
    throw new Error(detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
