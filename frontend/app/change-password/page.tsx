"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, errorMessage } from "@/lib/api";
import { getUser, updateUser } from "@/lib/auth";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Field";
import { Icon } from "@/components/layout/Icon";

export default function ChangePasswordPage() {
  const router = useRouter();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [ready, setReady] = useState(false);
  const [forced, setForced] = useState(false);

  /* eslint-disable react-hooks/set-state-in-effect -- one-time read of the locally
     stored session after mount: localStorage is unavailable during SSR/prerender,
     so this cannot be a lazy useState initialiser without a hydration mismatch. */
  useEffect(() => {
    const user = getUser();
    if (!user) {
      router.replace("/login");
      return;
    }
    setForced(Boolean(user.must_change_password));
    if (!user.must_change_password) {
      router.replace("/dashboard");
      return;
    }
    setReady(true);
  }, [router]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setFieldErrors({});
    if (next !== confirm) {
      setFieldErrors({ confirm: "Passwords do not match." });
      return;
    }
    setSubmitting(true);
    try {
      await api("/api/auth/change-password", {
        method: "POST",
        body: { current_password: current, new_password: next },
      });
      updateUser({ must_change_password: false });
      router.replace("/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fieldErrors);
        setFormError(err.message);
      } else {
        setFormError(errorMessage(err));
      }
      setSubmitting(false);
    }
  };

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-lg font-bold text-accent-ink">
            H
          </div>
          <div>
            <p className="text-lg font-semibold text-text">HCM Lite</p>
            <p className="text-xs text-muted">Account security</p>
          </div>
        </div>

        <div className="rounded-xl border border-border bg-surface p-6 shadow-[var(--shadow-card)] sm:p-8">
          <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-warning/15 text-warning">
            <Icon name="key" className="h-5 w-5" />
          </div>
          <h1 className="text-xl font-semibold tracking-tight text-text">Change your password</h1>
          <p className="mt-2 text-sm text-muted">
            {forced
              ? "Your temporary password must be changed before you can continue. This page is the only available action until the password is updated."
              : "Update the password on your account."}
          </p>

          <form onSubmit={onSubmit} className="mt-6 space-y-4" noValidate>
            {formError && (
              <div
                role="alert"
                className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
              >
                {formError}
              </div>
            )}

            <Field
              label="Current password"
              htmlFor="current_password"
              error={fieldErrors.current_password}
              required
            >
              <Input
                id="current_password"
                type="password"
                autoComplete="current-password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                required
              />
            </Field>

            <Field
              label="New password"
              htmlFor="new_password"
              error={fieldErrors.new_password}
              hint="Minimum length is enforced by the server."
              required
            >
              <Input
                id="new_password"
                type="password"
                autoComplete="new-password"
                value={next}
                onChange={(e) => setNext(e.target.value)}
                required
              />
            </Field>

            <Field label="Confirm new password" htmlFor="confirm_password" error={fieldErrors.confirm} required>
              <Input
                id="confirm_password"
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
              />
            </Field>

            <Button type="submit" className="w-full" size="lg" loading={submitting}>
              Save password &amp; continue
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
