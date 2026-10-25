"use client";

import { useMemo, useState } from "react";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useAuth } from "@/components/auth/Auth";
import { useApi } from "@/hooks/useApi";
import { asRows, toNum } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Field, Input, Select } from "@/components/ui/Field";
import { Icon } from "@/components/layout/Icon";
import type { Employee } from "@/types/api";

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

interface FormState {
  employee_code: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  address: string;
  department_id: string;
  designation_id: string;
  joining_date: string;
  employment_status: string;
  gender: string;
  basic_salary: string;
}

const EMPTY: FormState = {
  employee_code: "",
  first_name: "",
  last_name: "",
  email: "",
  phone: "",
  address: "",
  department_id: "",
  designation_id: "",
  joining_date: "",
  employment_status: "active",
  gender: "",
  basic_salary: "",
};

export function AddEmployeeModal({ open, onClose, onCreated }: Props) {
  const { user } = useAuth();
  // Brief matrix #05: only an Admin may create an HR login.
  const isAdmin = user?.role === "admin";
  const [loginRole, setLoginRole] = useState<"employee" | "hr">("employee");
  const [form, setForm] = useState<FormState>(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [created, setCreated] = useState<{ employee: Employee; temp_password: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const departments = useApi<{ items?: unknown[] } | unknown[]>(
    open ? "/api/org/departments" : null,
  );
  const designations = useApi<{ items?: unknown[] } | unknown[]>(
    open ? "/api/org/designations" : null,
  );

  const departmentOptions = useMemo(() => asRows(departments.data), [departments.data]);
  const designationOptions = useMemo(() => asRows(designations.data), [designations.data]);

  const set = (key: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const reset = () => {
    setForm(EMPTY);
    setFormError(null);
    setFieldErrors({});
    setCreated(null);
    setCopied(false);
  };

  const close = () => {
    onClose();
    setTimeout(reset, 200);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setFormError(null);
    setFieldErrors({});
    const payload: Record<string, unknown> = {
      employee_code: form.employee_code.trim(),
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      email: form.email.trim(),
      phone: form.phone.trim() || null,
      address: form.address.trim() || null,
      department_id: form.department_id ? toNum(form.department_id) : null,
      designation_id: form.designation_id ? toNum(form.designation_id) : null,
      joining_date: form.joining_date,
      employment_status: form.employment_status,
      basic_salary: form.basic_salary ? Number(form.basic_salary) : null,
    };
    if (form.gender) payload.gender = form.gender;
    if (loginRole === "hr") payload.create_login_role = "hr";

    try {
      const res = await api<{ employee: Employee; temp_password: string }>(
        "/api/employees",
        { method: "POST", body: payload },
      );
      setCreated(res);
      onCreated();
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fieldErrors);
        setFormError(err.status === 422 ? null : err.message);
      } else {
        setFormError(errorMessage(err));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const copyPassword = async () => {
    if (!created?.temp_password) return;
    try {
      await navigator.clipboard.writeText(created.temp_password);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={close}
      title={created ? "Employee created" : "Add employee"}
      description={
        created
          ? "The login account was created — share the temporary password securely."
          : "Creates the employee record and a login account in one step."
      }
      size="lg"
      footer={
        created ? (
          <Button onClick={close}>Done</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={close} disabled={submitting}>
              Cancel
            </Button>
            <Button onClick={submit} loading={submitting} type="submit" form="add-employee-form">
              Create employee
            </Button>
          </>
        )
      }
    >
      {created ? (
        <div className="space-y-4">
          <div className="rounded-lg border border-success/40 bg-success/10 px-4 py-3 text-sm text-success">
            {created.employee?.first_name ?? ""} {created.employee?.last_name ?? ""} was created
            with employee code {created.employee?.employee_code ?? "—"}.
          </div>
          <div>
            <p className="text-xs font-medium text-muted">Temporary password (shown once)</p>
            <div className="mt-2 flex items-center gap-2">
              <code className="flex-1 rounded-lg border border-border bg-surface-2 px-3 py-2 font-mono text-sm text-text">
                {created.temp_password}
              </code>
              <Button variant="secondary" onClick={copyPassword} aria-label="Copy password">
                <Icon name={copied ? "check" : "copy"} className="h-4 w-4" />
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
            <p className="mt-2 text-xs text-muted">
              The employee must change this password at first sign-in.
            </p>
          </div>
        </div>
      ) : (
        <form id="add-employee-form" onSubmit={submit} className="space-y-4" noValidate>
          {formError && (
            <div role="alert" className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
              {formError}
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Employee code" htmlFor="employee_code" error={fieldErrors.employee_code} required>
              <Input id="employee_code" value={form.employee_code} onChange={set("employee_code")} placeholder="EMP-001" required />
            </Field>
            <Field label="First name" htmlFor="first_name" error={fieldErrors.first_name} required>
              <Input id="first_name" value={form.first_name} onChange={set("first_name")} required />
            </Field>
            <Field label="Last name" htmlFor="last_name" error={fieldErrors.last_name} required>
              <Input id="last_name" value={form.last_name} onChange={set("last_name")} required />
            </Field>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Email" htmlFor="email" error={fieldErrors.email} required>
              <Input id="email" type="email" value={form.email} onChange={set("email")} placeholder="person@company.com" required />
            </Field>
            <Field label="Phone" htmlFor="phone" error={fieldErrors.phone}>
              <Input id="phone" value={form.phone} onChange={set("phone")} placeholder="+92 300 0000000" />
            </Field>
          </div>

          <Field label="Address" htmlFor="address" error={fieldErrors.address}>
            <Input id="address" value={form.address} onChange={set("address")} placeholder="Street, city" />
          </Field>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Department" htmlFor="department_id" error={fieldErrors.department_id} required>
              <Select id="department_id" value={form.department_id} onChange={set("department_id")} required>
                <option value="">Select department…</option>
                {departmentOptions.map((d) => (
                  <option key={String(d.id)} value={String(d.id)}>
                    {String(d.name ?? d.id)}
                  </option>
                ))}
                {departmentOptions.length === 0 && !departments.loading && (
                  <option value="" disabled>
                    No departments — create one in Settings
                  </option>
                )}
              </Select>
            </Field>
            <Field label="Designation" htmlFor="designation_id" error={fieldErrors.designation_id} required>
              <Select id="designation_id" value={form.designation_id} onChange={set("designation_id")} required>
                <option value="">Select designation…</option>
                {designationOptions.map((d) => (
                  <option key={String(d.id)} value={String(d.id)}>
                    {String(d.name ?? d.id)}
                  </option>
                ))}
                {designationOptions.length === 0 && !designations.loading && (
                  <option value="" disabled>
                    No designations — create one in Settings
                  </option>
                )}
              </Select>
            </Field>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Joining date" htmlFor="joining_date" error={fieldErrors.joining_date} required>
              <Input id="joining_date" type="date" value={form.joining_date} onChange={set("joining_date")} required />
            </Field>
            <Field label="Employment status" htmlFor="employment_status" error={fieldErrors.employment_status}>
              <Select id="employment_status" value={form.employment_status} onChange={set("employment_status")}>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
                <option value="terminated">Terminated</option>
              </Select>
            </Field>
            <Field label="Gender" htmlFor="gender" error={fieldErrors.gender} hint="Optional">
              <Select id="gender" value={form.gender} onChange={set("gender")}>
                <option value="">Not specified</option>
                <option value="male">Male</option>
                <option value="female">Female</option>
                <option value="other">Other</option>
              </Select>
            </Field>
          </div>

          <Field
            label="Basic salary (per year, PKR)"
            htmlFor="basic_salary"
            error={fieldErrors.basic_salary}
            hint="Drives HRA (40%), medical (10%) and gross (1.5×) in payroll."
          >
            <Input id="basic_salary" type="number" min="0" step="0.01" value={form.basic_salary} onChange={set("basic_salary")} placeholder="1200000" />
          </Field>

          {isAdmin && (
            <Field
              label="Create login as"
              htmlFor="login_role"
              hint="Admin-only: an HR login gets the HR role (approve leave, manage payroll)."
            >
              <Select
                id="login_role"
                value={loginRole}
                onChange={(e) => setLoginRole(e.target.value === "hr" ? "hr" : "employee")}
              >
                <option value="employee">Employee login</option>
                <option value="hr">HR login</option>
              </Select>
            </Field>
          )}
        </form>
      )}
    </Modal>
  );
}
