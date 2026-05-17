"use client";

import { LoaderCircle, Trash2 } from "lucide-react";
import Link from "next/link";

import { formatDateTime } from "@/lib/format";
import type { Notification } from "@/lib/types";

type NotificationItemProps = {
  notification: Notification;
  isDeleting: boolean;
  onDelete: () => void;
};

const levelStyles = {
  info: "border-cyan-500/30 bg-cyan-500/10 text-cyan-200",
  success: "border-emerald-500/30 bg-emerald-500/10 text-emerald-200",
  warning: "border-amber-500/30 bg-amber-500/10 text-amber-200",
  error: "border-rose-500/30 bg-rose-500/10 text-rose-200",
} as const;

export function NotificationItem({
  notification,
  isDeleting,
  onDelete,
}: NotificationItemProps) {
  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.18em] ${levelStyles[notification.level]}`}
            >
              {notification.level}
            </span>
            <span className="rounded-full border border-white/10 px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-300">
              {notification.category}
            </span>
            <span className="text-xs text-slate-500">
              {formatDateTime(notification.created_at)}
            </span>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white">
              {notification.title}
            </h3>
            {notification.message ? (
              <p className="mt-1 text-sm leading-6 text-slate-300">
                {notification.message}
              </p>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-3 text-xs text-slate-400">
            {notification.related_job_id ? (
              <Link
                href={`/jobs/${notification.related_job_id}`}
                className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-2.5 py-1 text-cyan-200 transition hover:bg-cyan-400/20"
              >
                Job {notification.related_job_id.slice(0, 8)}
              </Link>
            ) : null}
            {notification.related_asset_id ? (
              <span className="rounded-full border border-white/10 px-2.5 py-1">
                Asset {notification.related_asset_id.slice(0, 8)}
              </span>
            ) : null}
          </div>
        </div>

        <button
          type="button"
          onClick={onDelete}
          disabled={isDeleting}
          className="rounded-full border border-white/10 p-2 text-slate-400 transition hover:border-rose-500/30 hover:bg-rose-500/10 hover:text-rose-200 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isDeleting ? (
            <LoaderCircle className="h-4 w-4 animate-spin" />
          ) : (
            <Trash2 className="h-4 w-4" />
          )}
        </button>
      </div>
    </article>
  );
}
