"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { fetchCurrentUser, getStoredUser, refreshSession } from "@/lib/api/auth";
import { clearSession, loadSession } from "@/lib/auth-store";
import type { User } from "@/lib/types";

export function useSessionBootstrap() {
  const queryClient = useQueryClient();
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [accessReady, setAccessReady] = useState(Boolean(loadSession()));

  useEffect(() => {
    let cancelled = false;

    const bootstrap = async () => {
      const stored = loadSession();
      if (!stored) {
        if (!cancelled) {
          setAccessReady(false);
          setIsBootstrapping(false);
        }
        return;
      }

      try {
        if (stored.expiresAt <= Date.now()) {
          await refreshSession();
        }
        await queryClient.prefetchQuery({
          queryKey: ["auth", "me"],
          queryFn: fetchCurrentUser,
        });
        if (!cancelled) {
          setAccessReady(true);
        }
      } catch {
        clearSession();
        if (!cancelled) {
          setAccessReady(false);
        }
      } finally {
        if (!cancelled) {
          setIsBootstrapping(false);
        }
      }
    };

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, [queryClient]);

  const currentUserQuery = useQuery({
    queryKey: ["auth", "me"],
    queryFn: fetchCurrentUser,
    enabled: accessReady,
    initialData: getStoredUser() ?? undefined,
  });

  return {
    queryClient,
    isBootstrapping,
    accessReady,
    setAccessReady,
    currentUser: currentUserQuery.data as User | undefined,
    currentUserQuery,
  };
}
