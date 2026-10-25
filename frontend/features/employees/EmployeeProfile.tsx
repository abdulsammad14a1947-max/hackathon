"use client";

import { useEffect, useState } from "react";
import { useApi } from "@/hooks/useApi";
import { api } from "@/lib/api";
import { useAuth } from "@/components/auth/Auth";
import { asPage, asRows, isObject, pick, toNum, toStr, statusTone } from "@/lib/utils";
import {
  fmtDate,
  fmtDateTime,
  fmtHours,
  fmtMoney,
  fmtNumber,
  fmtTime,
  monthName,
} from "@/lib/format";
import type {
  Correction,
  Employee,
  LeaveRequest,
  Payslip,
} from "@/types/api";
import { Card } from "@/components/ui/Card";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { ErrorState, EmptyState } from "@/components/ui/States";
import { ListSkeleton, TableSkeleton, CardSkeleton } from "@/components/ui/Skeleton";
import { Table, TH, TD, TR } from "@/components/ui/Table";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Field, Input, Select } from "@/components/ui/Field";
import { Icon } from "@/components/layout/Icon";
import { useToast } from "@/components/ui/Toast";
import { ApiError, errorMessage } from "@/lib/api";

export interface EmployeeProfileProps {
  employeeId: number;
  isSelf: boolean;
  /** `full` = HR/Admin can edit everything, `contact` = self can edit phone/address only. */
  editMode: "full" | "contact" | "none";
}

function EditModal({
  open,
  onClose,
  mode,
  employee,
  employeeId,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  mode: "full" | "contact";
  employee: Employee;
  employeeId: number;
  onSaved: () => void;
}) {
  // The form state lives in a child that only mounts while the dialog is open,
  // so it is initialised fresh from the employee record on every open.
  if (!open) return null;
  return (
    <EditForm
      onClose={onClose}
      mode={mode}
      employee={employee}
      employeeId={employeeId}
      onSaved={onSaved}
    />
  );
}

function EditForm({
  onClose,
  mode,
  employee,
  employeeId,
  onSaved,
}: {
  onClose: () => void;
  mode: "full" | "contact";
  employee: Employee;
  employeeId: number;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [form, setForm] = useState<Record<string, string>>(() => ({
    phone: employee.phone ?? "",
    address: employee.address ?? "",
    first_name: employee.first_name ?? "",
    last_name: employee.last_name ?? "",
    email: employee.email ?? "",
    department_id: employee.department_id ? String(employee.department_id) : "",
    designation_id: employee.designation_id ? String(employee.designation_id) : "",
    joining_date: employee.joining_date ?? "",
    employment_status: String(employee.employment_status ?? "active"),
    gender: employee.gender ? String(employee.gender) : "",
    basic_salary:
      employee.basic_salary === null || employee.basic_salary === undefined
        ? ""
        : String(employee.basic_salary),
  }));
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const departments = useApi<unknown>(mode === "full" ? "/api/org/departments" : null);
  const designations = useApi<unknown>(mode === "full" ? "/api/org/designations" : null);

  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setErrors({});
    setFormError(null);
    try {
      if (mode === "full") {
        await api(`/api/employees/${employeeId}`, {
          method: "PATCH",
          body: {
            first_name: form.first_name,
            last_name: form.last_name,
            email: form.email,
            phone: form.phone || null,
            address: form.address || null,
            department_id: form.department_id ? Number(form.department_id) : null,
            designation_id: form.designation_id ? Number(form.designation_id) : null,
            joining_date: form.joining_date,
            employment_status: form.employment_status,
            gender: form.gender || null,
            basic_salary: form.basic_salary ? Number(form.basic_salary) : null,
          },
        });
      } else {
        await api("/api/employees/me", {
          method: "PATCH",
          body: { phone: form.phone || null, address: form.address || null },
        });
      }
      toast({ type: "success", message: "Profile updated." });
      onSaved();
      onClose();
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors);
        setFormError(err.message);
      } else {
        setFormError(errorMessage(err));
      }
    } finally {
      setSaving(false);
    }
  };

  const departmentsRows = asRows(departments.data);
  const designationRows = asRows(designations.data);

  return (
    <Modal
      open
      onClose={onClose}
      title={mode === "full" ? "Edit employee" : "Edit your contact details"}
      description={
        mode === "full"
          ? "All fields are written to the employee record and audit-logged."
          : "Employees may update their own phone number and address."
      }
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" form="edit-employee-form" loading={saving}>
            Save changes
          </Button>
        </>
      }
    >
      <form id="edit-employee-form" onSubmit={submit} className="space-y-4" noValidate>
        {formError && (
          <div role="alert" className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
            {formError}
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Phone" htmlFor="edit_phone" error={errors.phone}>
            <Input id="edit_phone" value={form.phone ?? ""} onChange={set("phone")} placeholder="+92 300 0000000" />
          </Field>
          <Field label="Address" htmlFor="edit_address" error={errors.address}>
            <Input id="edit_address" value={form.address ?? ""} onChange={set("address")} />
          </Field>
        </div>

        {mode === "full" && (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="First name" htmlFor="edit_first" error={errors.first_name} required>
                <Input id="edit_first" value={form.first_name ?? ""} onChange={set("first_name")} required />
              </Field>
              <Field label="Last name" htmlFor="edit_last" error={errors.last_name} required>
                <Input id="edit_last" value={form.last_name ?? ""} onChange={set("last_name")} required />
              </Field>
            </div>
            <Field label="Email" htmlFor="edit_email" error={errors.email} required>
              <Input id="edit_email" type="email" value={form.email ?? ""} onChange={set("email")} required />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Department" htmlFor="edit_dept" error={errors.department_id}>
                <Select id="edit_dept" value={form.department_id ?? ""} onChange={set("department_id")}>
                  <option value="">No department</option>
                  {departmentsRows.map((d) => (
                    <option key={String(d.id)} value={String(d.id)}>
                      {toStr(d, String(d.id))}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Designation" htmlFor="edit_desig" error={errors.designation_id}>
                <Select id="edit_desig" value={form.designation_id ?? ""} onChange={set("designation_id")}>
                  <option value="">No designation</option>
                  {designationRows.map((d) => (
                    <option key={String(d.id)} value={String(d.id)}>
                      {toStr(d, String(d.id))}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Joining date" htmlFor="edit_join" error={errors.joining_date}>
                <Input id="edit_join" type="date" value={form.joining_date ?? ""} onChange={set("joining_date")} />
              </Field>
              <Field label="Status" htmlFor="edit_status" error={errors.employment_status}>
                <Select id="edit_status" value={form.employment_status ?? "active"} onChange={set("employment_status")}>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                  <option value="terminated">Terminated</option>
                </Select>
              </Field>
              <Field label="Gender" htmlFor="edit_gender" error={errors.gender}>
                <Select id="edit_gender" value={form.gender ?? ""} onChange={set("gender")}>
                  <option value="">Not specified</option>
                  <option value="male">Male</option>
                  <option value="female">Female</option>
                  <option value="other">Other</option>
                </Select>
              </Field>
            </div>
            <Field label="Basic salary (PKR)" htmlFor="edit_salary" error={errors.basic_salary}>
              <Input
                id="edit_salary"
                type="number"
                min="0"
                step="0.01"
                value={form.basic_salary ?? ""}
                onChange={set("basic_salary")}
              />
            </Field>
          </>
        )}
      </form>
    </Modal>
  );
}

function Salary({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "") {
    return <span className="text-xs text-muted">Not visible to your role</span>;
  }
  return <span className="tabular-nums text-text">{fmtMoney(value as number | string)}</span>;
}

function InfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border py-3 last:border-b-0">
      <dt className="text-xs font-medium uppercase tracking-wider text-muted">{label}</dt>
      <dd className="text-right text-sm text-text">{children}</dd>
    </div>
  );
}

/* ------------------------------- attendance ------------------------------- */

function AttendanceSection({ isSelf }: { isSelf: boolean }) {
  const now = new Date();
  const { data, loading, error, reload, errorMessage } = useApi<unknown>(
    isSelf
      ? `/api/attendance/me?year=${now.getFullYear()}&month=${now.getMonth() + 1}`
      : null,
  );

  if (!isSelf) {
    return (
      <EmptyState
        title="Attendance is personal to each employee"
        description="Attendance records for other employees are shown on the Attendance day board, filtered by department."
      />
    );
  }
  if (error) return <ErrorState message={errorMessage} onRetry={reload} />;
  if (loading && !data) return <ListSkeleton rows={4} />;

  const rows = asRows(isObject(data) ? (data.records ?? data.items ?? data) : data)
    .map((r) => ({
      date: toStr(pick(r, ["date", "day"]), "—"),
      status: toStr(pick(r, ["status"]), "—"),
      check_in: toStr(pick(r, ["check_in", "in"]), ""),
      check_out: toStr(pick(r, ["check_out", "out"]), ""),
      hours: toNum(pick(r, ["worked_hours", "hours"]), 0),
    }))
    .filter((r) => r.date !== "—")
    .sort((a, b) => (a.date < b.date ? 1 : -1))
    .slice(0, 10);

  const summary = isObject(data) && isObject(data.summary) ? (data.summary as Record<string, unknown>) : {};

  if (rows.length === 0) {
    return (
      <EmptyState
        title="No attendance this month"
        description="Records appear after you check in from the Attendance page."
      />
    );
  }

  return (
    <div className="space-y-4">
      {Object.keys(summary).length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Object.entries(summary).map(([key, value]) => (
            <div key={key} className="rounded-lg border border-border bg-surface-2 p-3">
              <p className="text-xs capitalize text-muted">{key.replace(/_/g, " ")}</p>
              <p className="text-lg font-semibold tabular-nums text-text">{fmtNumber(value as number)}</p>
            </div>
          ))}
        </div>
      )}
      <div className="overflow-hidden rounded-lg border border-border">
        <Table>
          <thead>
            <TR>
              <TH>Date</TH>
              <TH>Status</TH>
              <TH align="right">In</TH>
              <TH align="right">Out</TH>
              <TH align="right">Hours</TH>
            </TR>
          </thead>
          <tbody>
            {rows.map((r) => (
              <TR key={r.date}>
                <TD className="tabular-nums text-muted">{fmtDate(r.date)}</TD>
                <TD>
                  <Badge tone={statusTone(r.status)}>{r.status.replace(/_/g, " ")}</Badge>
                </TD>
                <TD align="right" className="tabular-nums">{fmtTime(r.check_in)}</TD>
                <TD align="right" className="tabular-nums">{fmtTime(r.check_out)}</TD>
                <TD align="right" className="tabular-nums">{fmtHours(r.hours)}</TD>
              </TR>
            ))}
          </tbody>
        </Table>
      </div>
      <p className="text-xs text-muted">
        Latest 10 records for {monthName(now.getMonth() + 1)} {now.getFullYear()}.
      </p>
    </div>
  );
}

/* ---------------------------------- leave --------------------------------- */

function normaliseLeave(value: unknown): LeaveRequest[] {
  return asPage<LeaveRequest>(value).items;
}

function leaveTypeLabel(row: LeaveRequest): string {
  const raw = (row as unknown as Record<string, unknown>).leave_type;
  if (typeof raw === "string") return raw;
  if (isObject(raw)) {
    return toStr(pick(raw, ["name", "code"]), "—");
  }
  return row.leave_type_code ?? "—";
}

function LeaveSection({ isSelf, employeeId }: { isSelf: boolean; employeeId: number }) {
  const path = isSelf
    ? "/api/leave/requests?scope=me&page=1&page_size=100"
    : "/api/leave/requests?scope=all&page=1&page_size=100";
  const { data, loading, error, reload, errorMessage } = useApi<unknown>(path);

  if (error) return <ErrorState message={errorMessage} onRetry={reload} />;
  if (loading && !data) return <ListSkeleton rows={3} />;

  let rows = normaliseLeave(data);
  if (!isSelf) {
    const hasEmployeeKey = rows.some((r) => {
      const raw = r as unknown as Record<string, unknown>;
      return raw.employee_id !== undefined || isObject(raw.employee);
    });
    if (hasEmployeeKey) {
      rows = rows.filter((r) => {
        const raw = r as unknown as Record<string, unknown>;
        if (raw.employee_id !== undefined) return toNum(raw.employee_id, -1) === employeeId;
        const emp = raw.employee as Record<string, unknown>;
        return isObject(emp) && toNum(emp.id, -1) === employeeId;
      });
    } else {
      rows = [];
    }
  }

  if (rows.length === 0) {
    return (
      <EmptyState
        title="No leave requests"
        description={isSelf ? "Request leave from the Leave page." : "This employee has not requested leave."}
      />
    );
  }

  return (
    <div className="space-y-3">
      {rows.map((row) => (
        <div
          key={row.id}
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface-2 px-4 py-3"
        >
          <div className="min-w-0">
            <p className="text-sm font-medium text-text">{leaveTypeLabel(row)}</p>
            <p className="text-xs text-muted">
              {fmtDate(row.start_date)} → {fmtDate(row.end_date)} ·{" "}
              {fmtNumber(row.working_days)} working day
              {toNum(row.working_days) === 1 ? "" : "s"}
            </p>
            {row.reason && <p className="mt-1 truncate text-xs text-muted/80">{row.reason}</p>}
          </div>
          <div className="flex items-center gap-3">
            <span className="text-[11px] text-muted/70">{fmtDate(row.created_at)}</span>
            <StatusBadge status={String(row.status)} />
          </div>
        </div>
      ))}
    </div>
  );
}

/* --------------------------------- payroll -------------------------------- */

interface PayrollRow {
  key: string;
  period: string;
  gross: number | string;
  net: number | string;
  tax?: number | string;
  deduction?: number | string;
  status?: string;
}

function toPayrollRows(items: unknown[], prefix: string): PayrollRow[] {
  return items
    .filter(isObject)
    .filter((r) => toNum(pick(r, ["period_month", "month"]), 0) >= 1)
    .map((r, i) => {
      const row = r as Record<string, unknown>;
      const month = toNum(pick(row, ["period_month", "month"]), 1);
      const year = toNum(pick(row, ["period_year", "year"]), 0);
      const rawStatus = toStr(pick(row, ["status"]), "");
      return {
        key: `${prefix}-${i}`,
        period: `${monthName(month)} ${year || ""}`.trim(),
        gross: toNum(pick(row, ["gross", "total_gross"]), 0),
        net: toNum(pick(row, ["net_pay", "total_net", "net"]), 0),
        tax: toNum(pick(row, ["tax"]), 0),
        deduction: toNum(pick(row, ["deduction_amount", "total_deductions"]), 0),
        status: rawStatus || "finalized",
      };
    });
}

/** Finalised payroll runs (max 8) derived from the runs page payload. */
function extractFinalizedRuns(runsData: unknown) {
  if (runsData === undefined) return [];
  return asPage<{ id: number; status: string; period_year: number; period_month: number }>(runsData)
    .items.filter((r) => String(r.status).toLowerCase() === "finalized")
    .slice(0, 8);
}

function PayrollSection({ isSelf, employeeId }: { isSelf: boolean; employeeId: number }) {
  const mine = useApi<unknown>(isSelf ? "/api/payroll/payslips/me" : null);
  const runs = useApi<unknown>(isSelf ? null : "/api/payroll/runs?page=1&page_size=20");

  const [otherRows, setOtherRows] = useState<PayrollRow[] | null>(null);
  const [otherLoading, setOtherLoading] = useState(!isSelf);
  const [otherError, setOtherError] = useState<string | null>(null);

  // Derived: runs arrived but none are finalised yet — no fetch is needed.
  const finalizedEmpty =
    !isSelf && runs.data !== undefined && extractFinalizedRuns(runs.data).length === 0;

  useEffect(() => {
    if (isSelf || runs.data === undefined) return;
    const finalized = extractFinalizedRuns(runs.data);
    if (!finalized.length) return;
    let cancelled = false;
    const load = async () => {
      try {
        const results = await Promise.all(
          finalized.map((run) =>
            api<unknown>(`/api/payroll/runs/${run.id}/items`)
              .then((payload) => ({
                run,
                items: asPage<Record<string, unknown>>(payload).items.filter(
                  (it) => toNum(it.employee_id, -1) === employeeId,
                ),
              }))
              .catch(() => ({ run, items: [] as Record<string, unknown>[] })),
          ),
        );
        if (cancelled) return;
        const rows: PayrollRow[] = [];
        results.forEach(({ run, items }) => {
          items.forEach((it, i) => {
            rows.push({
              key: `${run.id}-${i}`,
              period: `${monthName(run.period_month)} ${run.period_year}`,
              gross: toNum(it.gross, 0),
              net: toNum(it.net_pay, 0),
              tax: toNum(it.tax, 0),
              deduction: toNum(it.deduction_amount, 0),
              status: run.status,
            });
          });
        });
        setOtherRows(rows);
        setOtherError(null);
      } catch {
        if (!cancelled) setOtherError("Could not load payroll history.");
      } finally {
        if (!cancelled) setOtherLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [isSelf, employeeId, runs.data]);

  if (isSelf) {
    if (mine.error) return <ErrorState message={mine.errorMessage} onRetry={mine.reload} />;
    if (mine.loading && !mine.data) return <ListSkeleton rows={3} />;
    const rows = toPayrollRows(asPage<Payslip>(mine.data).items, "me");
    if (rows.length === 0) {
      return (
        <EmptyState title="No payslips yet" description="Payslips appear once payroll is finalized." />
      );
    }
    return <PayrollTable rows={rows} />;
  }

  if (runs.error) return <ErrorState message={runs.errorMessage} onRetry={runs.reload} />;
  if (!finalizedEmpty && (runs.loading || otherLoading) && otherRows === null) {
    return <ListSkeleton rows={3} />;
  }
  if (otherError) return <ErrorState message={otherError} onRetry={runs.reload} />;
  if (finalizedEmpty || !otherRows || otherRows.length === 0) {
    return (
      <EmptyState
        title="No finalized payroll yet"
        description="This employee's payslip rows appear after a payroll run is finalized."
      />
    );
  }
  return <PayrollTable rows={otherRows} />;
}

function PayrollTable({ rows }: { rows: PayrollRow[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <Table>
        <thead>
          <TR>
            <TH>Period</TH>
            <TH align="right">Gross</TH>
            <TH align="right">Deductions</TH>
            <TH align="right">Tax</TH>
            <TH align="right">Net pay</TH>
            <TH>Status</TH>
          </TR>
        </thead>
        <tbody>
          {rows.map((row) => (
            <TR key={row.key}>
              <TD className="font-medium text-text">{row.period}</TD>
              <TD align="right" className="tabular-nums">{fmtMoney(row.gross)}</TD>
              <TD align="right" className="tabular-nums">{fmtMoney(row.deduction ?? 0)}</TD>
              <TD align="right" className="tabular-nums">{fmtMoney(row.tax ?? 0)}</TD>
              <TD align="right" className="tabular-nums font-semibold text-text">
                {fmtMoney(row.net)}
              </TD>
              <TD>{row.status ? <StatusBadge status={row.status} /> : <Badge>Finalized</Badge>}</TD>
            </TR>
          ))}
        </tbody>
      </Table>
    </div>
  );
}

/* ------------------------------- corrections ------------------------------ */

export function CorrectionsList({ corrections, loading }: { corrections: Correction[]; loading: boolean }) {
  if (loading) return <ListSkeleton rows={2} />;
  if (corrections.length === 0) {
    return <EmptyState compact title="No correction requests" description="Submitted corrections will be listed here." />;
  }
  return (
    <div className="space-y-3">
      {corrections.map((c) => (
        <div key={c.id} className="rounded-lg border border-border bg-surface-2 px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-medium text-text">{fmtDate(c.attendance_date)}</p>
            <StatusBadge status={c.status} />
          </div>
          <p className="mt-1 text-xs text-muted">
            {fmtTime(c.requested_check_in)} → {fmtTime(c.requested_check_out)}
          </p>
          <p className="mt-1 text-xs text-muted/80">{c.reason}</p>
          {c.review_comment && (
            <p className="mt-1 text-xs text-muted">Reviewer: {c.review_comment}</p>
          )}
          {c.reviewed_at && (
            <p className="mt-1 text-[11px] text-muted/70">{fmtDateTime(c.reviewed_at)}</p>
          )}
        </div>
      ))}
    </div>
  );
}

/* --------------------------------- profile -------------------------------- */

export function EmployeeProfile({
  employeeId,
  isSelf,
  editMode,
}: EmployeeProfileProps) {
  const { data, loading, error, reload, errorMessage } = useApi<Employee>(
    `/api/employees/${employeeId}`,
  );
  const { user } = useAuth();
  const toast = useToast();
  const [tab, setTab] = useState<"employment" | "attendance" | "leave" | "payroll">(
    "employment",
  );
  const [editOpen, setEditOpen] = useState(false);
  // Brief matrix #05: Admin may reset/deactivate any login; HR only employee logins.
  const [loginAction, setLoginAction] = useState<null | "reset" | "deactivate" | "activate">(
    null,
  );
  const [loginBusy, setLoginBusy] = useState(false);
  const [tempPassword, setTempPassword] = useState<null | string>(null);

  if (error) return <ErrorState message={errorMessage} onRetry={reload} />;
  if (loading && !data) {
    return (
      <div className="space-y-4">
        <CardSkeleton />
        <TableSkeleton rows={5} cols={4} />
      </div>
    );
  }
  if (!data) return <ErrorState message="Employee not found." onRetry={reload} />;

  // ---- login account actions (brief matrix #05) --------------------------
  const loginRole = data.user_role ?? null;
  const loginActive = Boolean(data.user_is_active);
  const canManageLogin =
    !isSelf &&
    data.user_id != null &&
    (user?.role === "admin" ||
      (user?.role === "hr" && loginRole !== "admin" && loginRole !== "hr"));

  const runLoginAction = async () => {
    if (!loginAction) return;
    setLoginBusy(true);
    try {
      if (loginAction === "reset") {
        const res = await api<{ temp_password: string }>(
          `/api/employees/${employeeId}/reset-password`,
          { method: "POST", body: {} },
        );
        setTempPassword(res.temp_password);
        toast({ type: "success", message: "Password reset — a temporary password was issued." });
      } else {
        const action = loginAction === "deactivate" ? "deactivate" : "activate";
        await api(`/api/employees/${employeeId}/${action}`, { method: "POST", body: {} });
        toast({
          type: "success",
          message: `Login ${action === "deactivate" ? "deactivated" : "activated"}.`,
        });
        reload();
      }
    } catch (err) {
      toast({ type: "error", message: err instanceof ApiError ? err.message : String(err) });
    } finally {
      setLoginBusy(false);
      setLoginAction(null);
    }
  };

  const tabs = [
    { key: "employment", label: "Employment" },
    { key: "attendance", label: "Attendance" },
    { key: "leave", label: "Leave" },
    { key: "payroll", label: isSelf ? "Payslips" : "Payroll history" },
  ] as const;

  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-4">
            <span className="flex h-14 w-14 items-center justify-center rounded-xl bg-accent/20 text-lg font-semibold text-accent ring-1 ring-accent/40">
              {(data.full_name ?? `${data.first_name} ${data.last_name}`)
                .split(/\s+/)
                .filter(Boolean)
                .slice(0, 2)
                .map((p: string) => p[0])
                .join("")
                .toUpperCase()}
            </span>
            <div>
              <p className="text-xs font-mono text-muted">{data.employee_code}</p>
              <h2 className="text-xl font-semibold tracking-tight text-text">
                {data.full_name ?? `${data.first_name} ${data.last_name}`}
              </h2>
              <p className="mt-0.5 text-sm text-muted">
                {toStr(data.department, "No department")} · {toStr(data.designation, "No designation")}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={String(data.employment_status ?? "active")} />
            {isSelf && <Badge tone="accent">Your profile</Badge>}
            {canManageLogin && (
              <>
                <Badge tone={loginActive ? "neutral" : "warn"}>
                  {loginRole === "hr" || loginRole === "admin"
                    ? `${loginRole} login`
                    : "employee login"}
                  {loginActive ? "" : " · inactive"}
                </Badge>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setLoginAction("reset")}
                  disabled={loginBusy}
                >
                  Reset password
                </Button>
                {loginActive ? (
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => setLoginAction("deactivate")}
                    disabled={loginBusy}
                  >
                    Deactivate login
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="success"
                    onClick={() => setLoginAction("activate")}
                    disabled={loginBusy}
                  >
                    Activate login
                  </Button>
                )}
              </>
            )}
            {editMode !== "none" && (
              <Button onClick={() => setEditOpen(true)} variant="secondary">
                <Icon name="edit" className="h-4 w-4" />
                Edit profile
              </Button>
            )}
          </div>
        </div>
      </Card>

      <div role="tablist" aria-label="Employee sections" className="flex flex-wrap gap-1 border-b border-border">
        {tabs.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-4 py-2.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
              tab === t.key
                ? "border-accent text-text"
                : "border-transparent text-muted hover:text-text"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div>
        {tab === "employment" && (
          <Card title="Employment information">
            <dl>
              <InfoRow label="Employee code">
                <span className="font-mono">{data.employee_code}</span>
              </InfoRow>
              <InfoRow label="Email">{data.email}</InfoRow>
              <InfoRow label="Phone">
                {data.phone ? data.phone : <span className="text-xs text-muted">Not provided</span>}
              </InfoRow>
              <InfoRow label="Address">
                {data.address ? data.address : <span className="text-xs text-muted">Not provided</span>}
              </InfoRow>
              <InfoRow label="Department">{toStr(data.department, "—")}</InfoRow>
              <InfoRow label="Designation">{toStr(data.designation, "—")}</InfoRow>
              <InfoRow label="Joining date">{fmtDate(data.joining_date)}</InfoRow>
              <InfoRow label="Status">
                <StatusBadge status={String(data.employment_status ?? "active")} />
              </InfoRow>
              <InfoRow label="Gender">
                {data.gender ? data.gender : <span className="text-xs text-muted">—</span>}
              </InfoRow>
              <InfoRow label="Basic salary">
                <Salary value={data.basic_salary} />
              </InfoRow>
            </dl>
            <p className="mt-4 text-xs text-muted">
              {isSelf
                ? "Contact HR to change anything besides your phone number and address."
                : "Changes are made from the employee edit form; every change is audit-logged."}
            </p>
          </Card>
        )}
        {tab === "attendance" && (
          <Card title="Attendance summary" description={`Most recent records for ${data.employee_code}`}>
            <AttendanceSection isSelf={isSelf} />
          </Card>
        )}
        {tab === "leave" && (
          <Card title="Leave history" description={isSelf ? "Your requests" : "Requests by this employee"}>
            <LeaveSection isSelf={isSelf} employeeId={employeeId} />
          </Card>
        )}
        {tab === "payroll" && (
          <Card title="Payroll history" description="Finalized payroll runs only">
            <PayrollSection isSelf={isSelf} employeeId={employeeId} />
          </Card>
        )}
      </div>

      {editMode !== "none" && data && (
        <EditModal
          open={editOpen}
          onClose={() => setEditOpen(false)}
          mode={editMode}
          employee={data}
          employeeId={employeeId}
          onSaved={() => reload()}
        />
      )}

      {/* Login account actions — brief matrix #05 */}
      <Modal
        open={canManageLogin && loginAction !== null}
        onClose={() => setLoginAction(null)}
        title={
          loginAction === "reset"
            ? "Reset this login's password?"
            : loginAction === "deactivate"
              ? "Deactivate this login?"
              : "Activate this login?"
        }
        description={`${data.email} · ${loginRole ?? "employee"} login`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setLoginAction(null)} disabled={loginBusy}>
              Cancel
            </Button>
            <Button
              variant={loginAction === "deactivate" ? "danger" : "primary"}
              onClick={runLoginAction}
              loading={loginBusy}
            >
              {loginAction === "reset"
                ? "Reset password"
                : loginAction === "deactivate"
                  ? "Deactivate"
                  : "Activate"}
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted">
          {loginAction === "reset"
            ? "A temporary password is generated; the user must change it at next login. This is audit-logged."
            : loginAction === "deactivate"
              ? "The login is blocked immediately. Employee records are kept."
              : "The login can sign in again immediately."}
        </p>
      </Modal>

      <Modal
        open={tempPassword !== null}
        onClose={() => setTempPassword(null)}
        title="Temporary password"
        description={`${data.email} must change it at next login.`}
        footer={
          <Button variant="primary" onClick={() => setTempPassword(null)}>
            Done
          </Button>
        }
      >
        <p className="rounded-lg border border-border bg-surface-2 px-4 py-3 font-mono text-sm text-text">
          {tempPassword}
        </p>
      </Modal>
    </div>
  );
}
