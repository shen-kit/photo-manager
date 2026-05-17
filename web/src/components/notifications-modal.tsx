"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, LoaderCircle, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { NotificationItem } from "@/components/notification-item";
import { useToast } from "@/components/toast-provider";
import {
  clearNotifications,
  deleteNotification,
  getNotifications,
} from "@/lib/api/notifications";

type NotificationsModalProps = {
  open: boolean;
  onClose: () => void;
};

export function NotificationsModal({
  open,
  onClose,
}: NotificationsModalProps) {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    return () => setMounted(false);
  }, []);

  const notificationsQuery = useQuery({
    queryKey: ["notifications"],
    queryFn: getNotifications,
    enabled: open,
  });

  const deleteMutation = useMutation({
    mutationFn: async (notificationId: string) => {
      setDeletingId(notificationId);
      await deleteNotification(notificationId);
    },
    onSuccess: async () => {
      pushToast("Notification deleted", "info");
      await queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (error: Error) => {
      pushToast(error.message, "error");
    },
    onSettled: () => {
      setDeletingId(null);
    },
  });

  const clearMutation = useMutation({
    mutationFn: clearNotifications,
    onSuccess: async () => {
      pushToast("Notifications cleared", "info");
      await queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (error: Error) => {
      pushToast(error.message, "error");
    },
  });

  if (!open || !mounted) {
    return null;
  }

  const notifications = notificationsQuery.data ?? [];

  return createPortal(
    <div
      className="fixed inset-0 z-[120] overflow-y-auto bg-black/70 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div className="flex min-h-full items-center justify-center">
        <div
          className="flex max-h-[calc(100vh-2rem)] w-full max-w-3xl flex-col overflow-hidden rounded-3xl border border-white/10 bg-ink-900 shadow-panel"
          onClick={(event) => event.stopPropagation()}
        >
        <div className="flex items-center justify-between border-b border-white/10 px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-white">Notifications</h2>
            <p className="text-xs text-slate-400">
              Recent backend events and long-running job updates.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => clearMutation.mutate()}
              disabled={clearMutation.isPending || notifications.length === 0}
              className="flex items-center gap-2 rounded-2xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs font-medium text-rose-200 transition hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {clearMutation.isPending ? (
                <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Trash2 className="h-3.5 w-3.5" />
              )}
              Clear all
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-white/10 p-2 text-slate-300 transition hover:bg-white/10 hover:text-white"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {notificationsQuery.isLoading ? (
            <div className="flex min-h-full items-center justify-center text-sm text-slate-400">
              <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
              Loading notifications...
            </div>
          ) : null}

          {notificationsQuery.isError ? (
            <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
              {(notificationsQuery.error as Error).message}
            </div>
          ) : null}

          {!notificationsQuery.isLoading &&
          !notificationsQuery.isError &&
          notifications.length === 0 ? (
            <div className="flex min-h-full flex-col items-center justify-center gap-3 rounded-3xl border border-dashed border-white/10 text-center text-sm text-slate-500">
              <AlertTriangle className="h-5 w-5 text-slate-600" />
              No notifications yet.
            </div>
          ) : null}

          {notifications.length > 0 ? (
            <div className="space-y-3">
              {notifications.map((notification) => (
                <NotificationItem
                  key={notification.id}
                  notification={notification}
                  isDeleting={deletingId === notification.id}
                  onDelete={() => deleteMutation.mutate(notification.id)}
                />
              ))}
            </div>
          ) : null}
        </div>
      </div>
      </div>
    </div>
    ,
    document.body,
  );
}
