"use client";

import { useMutation } from "@tanstack/react-query";
import { Home, LoaderCircle, LogOut, Workflow } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { NotificationsButton } from "@/components/notifications-button";
import { useToast } from "@/components/toast-provider";
import { logout } from "@/lib/api/auth";
import { clearSession } from "@/lib/auth-store";
import type { User } from "@/lib/types";

type AppShellProps = {
  currentUser: User;
  title: string;
  description: string;
  children: ReactNode;
  headerActions?: ReactNode;
};

export function AppShell({
  currentUser,
  title,
  description,
  children,
  headerActions,
}: AppShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { pushToast } = useToast();

  const logoutMutation = useMutation({
    mutationFn: logout,
    onSuccess: () => {
      clearSession();
      pushToast("Signed out", "info");
      router.push("/");
      router.refresh();
    },
    onError: (error: Error) => {
      pushToast(error.message, "error");
    },
  });

  const navLinkClass = (href: string) => {
    const isActive =
      href === "/jobs" ? pathname.startsWith("/jobs") : pathname === href;
    return `flex items-center gap-2 rounded-2xl border px-4 py-3 text-sm transition ${
      isActive
        ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-200"
        : "border-white/10 bg-white/[0.03] text-slate-300 hover:bg-white/[0.07]"
    }`;
  };

  return (
    <main className="min-h-screen bg-mesh-grid bg-grid-size">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-4 md:px-6 lg:px-8">
        <header className="rounded-[28px] border border-white/10 bg-black/25 px-6 py-5 shadow-panel backdrop-blur">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-cyan-300">
                Photo Manager
              </p>
              <h1 className="mt-2 text-2xl font-semibold text-white">{title}</h1>
              <p className="mt-2 text-sm text-slate-400">
                Signed in as{" "}
                <span className="text-slate-200">{currentUser.username}</span>.{" "}
                {description}
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              {headerActions}
              <Link href="/" className={navLinkClass("/")}>
                <Home className="h-4 w-4" />
                Dashboard
              </Link>
              <Link href="/jobs" className={navLinkClass("/jobs")}>
                <Workflow className="h-4 w-4" />
                Jobs
              </Link>
              <NotificationsButton />
              <button
                type="button"
                onClick={() => logoutMutation.mutate()}
                className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-slate-300 transition hover:bg-white/[0.07]"
              >
                {logoutMutation.isPending ? (
                  <LoaderCircle className="h-4 w-4 animate-spin" />
                ) : (
                  <LogOut className="h-4 w-4" />
                )}
                Logout
              </button>
            </div>
          </div>
        </header>

        {children}
      </div>
    </main>
  );
}
