"use client";

import { useMutation } from "@tanstack/react-query";
import { LoaderCircle, UserRound } from "lucide-react";
import { useState } from "react";

import { useToast } from "@/components/toast-provider";
import { login } from "@/lib/api/auth";

type LoginScreenProps = {
  onLoggedIn: () => Promise<void> | void;
};

type LoginFormState = {
  username: string;
  password: string;
};

export function LoginScreen({ onLoggedIn }: LoginScreenProps) {
  const { pushToast } = useToast();
  const [loginForm, setLoginForm] = useState<LoginFormState>({
    username: "",
    password: "",
  });

  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: async () => {
      await onLoggedIn();
      pushToast("Login complete", "success");
    },
    onError: (error: Error) => {
      pushToast(error.message, "error");
    },
  });

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <section className="w-full max-w-md rounded-[28px] border border-white/10 bg-ink-900/90 p-8 shadow-panel backdrop-blur">
        <div className="mb-8 space-y-3">
          <span className="inline-flex rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-xs uppercase tracking-[0.24em] text-cyan-300">
            Developer Dashboard
          </span>
          <h1 className="text-3xl font-semibold text-white">
            FastAPI Photo Manager Ops
          </h1>
          <p className="text-sm leading-6 text-slate-400">
            Authenticate with your API user to trigger scans, inspect jobs, and
            review notifications.
          </p>
        </div>

        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            loginMutation.mutate(loginForm);
          }}
        >
          <label className="block space-y-2">
            <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
              Username
            </span>
            <input
              value={loginForm.username}
              onChange={(event) =>
                setLoginForm((current) => ({
                  ...current,
                  username: event.target.value,
                }))
              }
              className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-400/50"
              placeholder="testuser"
            />
          </label>

          <label className="block space-y-2">
            <span className="text-xs uppercase tracking-[0.2em] text-slate-500">
              Password
            </span>
            <input
              type="password"
              value={loginForm.password}
              onChange={(event) =>
                setLoginForm((current) => ({
                  ...current,
                  password: event.target.value,
                }))
              }
              className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-400/50"
              placeholder="••••••••"
            />
          </label>

          <button
            type="submit"
            disabled={loginMutation.isPending}
            className="flex w-full items-center justify-center gap-2 rounded-2xl bg-cyan-400 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loginMutation.isPending ? (
              <LoaderCircle className="h-4 w-4 animate-spin" />
            ) : (
              <UserRound className="h-4 w-4" />
            )}
            Sign In
          </button>
        </form>
      </section>
    </main>
  );
}
