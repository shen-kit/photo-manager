import { apiRequest } from "@/lib/api/client";
import type { Notification } from "@/lib/types";

export function getNotifications() {
  return apiRequest<Notification[]>("/api/v1/notifications", {
    auth: true,
  });
}

export function deleteNotification(notificationId: string) {
  return apiRequest<void>(`/api/v1/notifications/${notificationId}`, {
    method: "DELETE",
    auth: true,
    contentType: null,
  });
}

export function clearNotifications() {
  return apiRequest<void>("/api/v1/notifications", {
    method: "DELETE",
    auth: true,
    contentType: null,
  });
}
