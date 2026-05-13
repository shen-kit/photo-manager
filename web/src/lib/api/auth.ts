import { clearSession, loadSession, saveSession } from "@/lib/auth-store";
import { apiRequest } from "@/lib/api/client";
import type { AuthResponse, User } from "@/lib/types";

type LoginPayload = {
  username: string;
  password: string;
};

function persistAuth(payload: AuthResponse) {
  saveSession({
    accessToken: payload.access_token,
    expiresAt: Date.now() + payload.expires_in * 1000,
    user: payload.user,
  });
}

export async function login(payload: LoginPayload) {
  const response = await apiRequest<AuthResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
    auth: false,
  });
  persistAuth(response);
  return response;
}

export async function refreshSession() {
  const response = await apiRequest<AuthResponse>("/api/v1/auth/refresh", {
    method: "POST",
    auth: false,
    contentType: null,
  });
  persistAuth(response);
  return response;
}

export async function fetchCurrentUser() {
  return apiRequest<User>("/api/v1/auth/me", {
    auth: true,
  });
}

export async function logout() {
  await apiRequest<void>("/api/v1/auth/logout", {
    method: "POST",
    auth: false,
    contentType: null,
  });
  clearSession();
}

export function getStoredUser() {
  return loadSession()?.user ?? null;
}
