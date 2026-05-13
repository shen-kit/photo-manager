"use client";

import { CheckCircle2, Info, TriangleAlert, X } from "lucide-react";
import type { ReactNode } from "react";
import { createContext, useContext, useMemo, useState } from "react";

type ToastTone = "success" | "error" | "info";

type Toast = {
  id: number;
  title: string;
  tone: ToastTone;
};

type ToastContextValue = {
  pushToast: (title: string, tone?: ToastTone) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

const toneStyles: Record<ToastTone, string> = {
  success: "border-emerald-500/40 bg-emerald-500/10 text-emerald-100",
  error: "border-rose-500/40 bg-rose-500/10 text-rose-100",
  info: "border-cyan-500/40 bg-cyan-500/10 text-cyan-100",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const value = useMemo<ToastContextValue>(
    () => ({
      pushToast(title, tone = "info") {
        const id = Date.now() + Math.random();
        setToasts((current) => [...current, { id, title, tone }]);
        window.setTimeout(() => {
          setToasts((current) => current.filter((toast) => toast.id !== id));
        }, 3200);
      },
    }),
    [],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed right-4 top-4 z-50 flex w-full max-w-sm flex-col gap-3">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`pointer-events-auto flex items-center gap-3 rounded-2xl border px-4 py-3 shadow-panel backdrop-blur ${toneStyles[toast.tone]}`}
          >
            {toast.tone === "success" ? <CheckCircle2 className="h-4 w-4" /> : null}
            {toast.tone === "error" ? <TriangleAlert className="h-4 w-4" /> : null}
            {toast.tone === "info" ? <Info className="h-4 w-4" /> : null}
            <span className="flex-1 text-sm">{toast.title}</span>
            <button
              type="button"
              className="rounded-full p-1 text-current/70 transition hover:bg-white/10 hover:text-current"
              onClick={() => setToasts((current) => current.filter((item) => item.id !== toast.id))}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within ToastProvider");
  }
  return context;
}
