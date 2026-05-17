"use client";

import { Bell } from "lucide-react";
import { useState } from "react";

import { NotificationsModal } from "@/components/notifications-modal";

export function NotificationsButton() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-slate-300 transition hover:bg-white/[0.07]"
      >
        <Bell className="h-4 w-4" />
        Notifications
      </button>
      <NotificationsModal open={open} onClose={() => setOpen(false)} />
    </>
  );
}
