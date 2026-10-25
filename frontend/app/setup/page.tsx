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

export default function SetupPage() {
  const router = useRouter();
  const [companyName, setCompanyName] = useState("");
  const [adminName, setAdminName] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [alreadySetup, setAlreadySetup] = useState(false);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const user = getUser();
    if (user && !user.must_change_password) {
      router.replace("/dashboard");
      return;
    }
    api<SetupStatus>("/api/setup/status")
      .then((status) => setAlreadySetup(!status?.needs_setup))
      .catch(() => setAlreadySetup(false))
      .finally(() => setChecking(false));
  }, [router]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirm) {
      setFieldErrors((f) => ({ ...f, confirm: "Passwords do not match." }));
      return;
    }
    setSubmitting(true);
    setFormError(null);
    setFieldErrors({});
    try {
      const res = await api<LoginResponse>("/api/setup/company", {
        method: "POST",
        body: {
          company_name: companyName.trim(),
          admin: {
            full_name: adminName.trim(),
            email: adminEmail.trim(),
            password,
          },
        },
      });
      setSession(res.access_token, {
        ...res.user,
        must_change_password: Boolean(res.must_change_password),
      });
      router.replace("/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fieldErrors);
        if (err.status === 409) {
          setAlreadySetup(true);
          setFormError("This instance has already been set up. Please sign in instead.");
        } else {
          setFormError(err.message);
        }
      } else {
        setFormError(errorMessage(err));
      }
      setSubmitting(false);
    }
  };

  if (checking) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      </div>
    );
  }

  if (alreadySetup) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg px-4">
        <div className="w-full max-w-md rounded-xl border border-border bg-surface p-8 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-info/15 text-info">
            <Icon name="info" className="h-6 w-6" />
          </div>
          <h1 className="text-xl font-semibold text-text">Already set up</h1>
          <p className="mt-2 text-sm text-muted">
            This HCM Lite instance has already been provisioned, so first-run setup is closed.
            Sign in with your administrator account instead.
          </p>
          <Link href="/login" className="mt-6 inline-block">
            <Button>Go to sign in</Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4 py-12">
      <div className="w-full max-w-xl">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-lg font-bold text-accent-ink">
            H
          </div>
          <div>
            <p className="text-lg font-semibold text-text">Welcome to HCM Lite</p>
            <p className="text-xs text-muted">First-run company setup — takes about a minute.</p>
          </div>
        </div>

        <div className="rounded-xl border border-border bg-surface p-6 shadow-[var(--shadow-card)] sm:p-8">
          <h1 className="text-xl font-semibold tracking-tight text-text">Create your company</h1>
          <p className="mt-1 text-sm text-muted">
            This creates the tenant, default leave types, office settings and the first admin
            account.
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
              label="Company name"
              htmlFor="company_name"
              error={fieldErrors.company_name}
              required
            >
              <Input
                id="company_name"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                placeholder="Acme Manufacturing (Pvt) Ltd"
                required
              />
            </Field>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Admin full name" htmlFor="admin_name" error={fieldErrors["admin.full_name"]} required>
                <Input
                  id="admin_name"
                  value={adminName}
                  onChange={(e) => setAdminName(e.target.value)}
                  placeholder="Ayesha Khan"
                  required
                />
              </Field>
              <Field label="Admin email" htmlFor="admin_email" error={fieldErrors["admin.email"]} required>
                <Input
                  id="admin_email"
                  type="email"
                  value={adminEmail}
                  onChange={(e) => setAdminEmail(e.target.value)}
                  placeholder="admin@company.com"
                  required
                />
              </Field>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field
                label="Admin password"
                htmlFor="admin_password"
                error={fieldErrors["admin.password"]}
                hint="Used for the first sign-in."
                required
              >
                <Input
                  id="admin_password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  minLength={6}
                  required
                />
              </Field>
              <Field
                label="Confirm password"
                htmlFor="admin_confirm"
                error={fieldErrors.confirm}
                required
              >
                <Input
                  id="admin_confirm"
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  minLength={6}
                  required
                />
              </Field>
            </div>

            <Button type="submit" className="w-full" size="lg" loading={submitting}>
              Create company &amp; sign in
            </Button>
          </form>
        </div>

        <p className="mt-4 text-center text-xs text-muted">
          Already provisioned?{" "}
          <Link href="/login" className="font-medium text-accent hover:text-accent-hover">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
