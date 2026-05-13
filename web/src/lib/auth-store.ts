const ACCESS_TOKEN_KEY = "photo-manager.access-token";
const ACCESS_EXPIRY_KEY = "photo-manager.access-expiry";
const USER_KEY = "photo-manager.user";

type StoredUser = {
  id: string;
  username: string;
  is_active: boolean;
};

export type StoredSession = {
  accessToken: string;
  expiresAt: number;
  user: StoredUser;
};

export function loadSession(): StoredSession | null {
  if (typeof window === "undefined") {
    return null;
  }

  const accessToken = window.localStorage.getItem(ACCESS_TOKEN_KEY);
  const expiresAt = window.localStorage.getItem(ACCESS_EXPIRY_KEY);
  const user = window.localStorage.getItem(USER_KEY);

  if (!accessToken || !expiresAt || !user) {
    return null;
  }

  try {
    return {
      accessToken,
      expiresAt: Number(expiresAt),
      user: JSON.parse(user) as StoredUser,
    };
  } catch {
    clearSession();
    return null;
  }
}

export function saveSession(session: StoredSession) {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(ACCESS_TOKEN_KEY, session.accessToken);
  window.localStorage.setItem(ACCESS_EXPIRY_KEY, String(session.expiresAt));
  window.localStorage.setItem(USER_KEY, JSON.stringify(session.user));
}

export function clearSession() {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(ACCESS_EXPIRY_KEY);
  window.localStorage.removeItem(USER_KEY);
}
