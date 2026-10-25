"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, errorMessage } from "@/lib/api";
import { setSession, getUser } from "@/lib/auth";
import type { LoginResponse, SetupStatus } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Field";
import { Icon } from "@/components/layout/Icon";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [needsSetup, setNeedsSetup] = useState(false);

  useEffect(() => {
    const user = getUser();
    if (user) {
      router.replace(user.must_change_password ? "/change-password" : "/dashboard");
      return;
    }
    api<SetupStatus>("/api/setup/status")
      .then((status) => setNeedsSetup(Boolean(status?.needs_setup)))
      .catch(() => setNeedsSetup(false));
  }, [router]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setFormError(null);
    setFieldErrors({});
    try {
      const res = await api<LoginResponse>("/api/auth/login", {
        method: "POST",
        body: { email: email.trim(), password },
      });
      setSession(res.access_token, {
        ...res.user,
        must_change_password: Boolean(res.must_change_password),
      });
      router.replace(res.must_change_password ? "/change-password" : "/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fieldErrors);
        setFormError(
          err.status === 401
            ? "Invalid email or password. Please check your credentials and try again."
            : err.message,
        );
      } else {
        setFormError(errorMessage(err));
      }
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-bg">
      {/* Brand panel */}
      <aside className="hidden w-1/2 flex-col justify-between border-r border-border bg-surface p-10 lg:flex">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-lg font-bold text-accent-ink">
            H
          </div>
          <div>
            <p className="text-lg font-semibold text-text">HCM Lite</p>
            <p className="text-xs text-muted">AI-assisted Human Capital Management</p>
          </div>
        </div>
        <div className="max-w-md">
          <h1 className="text-3xl font-semibold leading-tight tracking-tight text-text">
            Attendance, leave and payroll in one place.
          </h1>
          <ul className="mt-8 space-y-4 text-sm text-muted">
            {[
              ["attendance", "Geofenced check-in/out with monthly status calendar"],
              ["leave", "Quota-aware leave requests with approval inbox"],
              ["payroll", "Draft-to-finalized payroll runs and payslip PDFs"],
              ["assistant", "AI assistant that drafts leave requests for your confirmation"],
            ].map(([icon, text]) => (
              <li key={text} className="flex items-start gap-3">
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-accent ring-1 ring-accent/30">
                  <Icon name={icon} className="h-4 w-4" />
                </span>
                {text}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-muted">
          Roles: Administrator · HR · Employee — each sees its own dashboard.
        </p>
      </aside>

      {/* Form */}
      <main className="flex flex-1 items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-md">
          <div className="mb-8 lg:hidden">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-lg font-bold text-accent-ink">
                H
              </div>
              <div>
                <p className="text-lg font-semibold text-text">HCM Lite</p>
                <p className="text-xs text-muted">Human Capital Management</p>
              </div>
            </div>
          </div>

          <h2 className="text-2xl font-semibold tracking-tight text-text">Sign in</h2>
          <p className="mt-1 text-sm text-muted">Use the credentials issued by your HR team.</p>

          <form onSubmit={onSubmit} className="mt-8 space-y-4" noValidate>
            {formError && (
              <div
                role="alert"
                className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
              >
                {formError}
              </div>
            )}

            <Field label="Email address" htmlFor="email" error={fieldErrors.email} required>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                placeholder="you@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </Field>

            <Field label="Password" htmlFor="password" error={fieldErrors.password} required>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </Field>

            <Button type="submit" className="w-full" loading={submitting} size="lg">
              Sign in
            </Button>
          </form>

          <div className="mt-6 text-xs text-muted">
            {needsSetup ? (
              <Link
                href="/setup"
                className="font-medium text-accent hover:text-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded"
              >
                First run? Set up your company →
              </Link>
            ) : (
              <span>Company already provisioned.</span>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
