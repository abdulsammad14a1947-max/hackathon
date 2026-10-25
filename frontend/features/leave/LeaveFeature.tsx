"use client";

import { useMemo, useState } from "react";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useAuth } from "@/components/auth/Auth";
import { useApi } from "@/hooks/useApi";
import { fmtDate, currentYear, todayISO } from "@/lib/format";
import { asPage, previewWorkingDays, toNum } from "@/lib/utils";
import type { LeaveBalance, LeaveRequest, LeaveType } from "@/types/api";
import { Card, StatCard } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/Badge";
import { Field, Input, Select, Textarea } from "@/components/ui/Field";
import { Modal, ConfirmDialog } from "@/components/ui/Modal";
import { ErrorState, EmptyState } from "@/components/ui/States";
import { ListSkeleton, StatsSkeleton } from "@/components/ui/Skeleton";
import { Pagination, TableContainer, Table, TH, TD, TR } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

/* ----------------------------- shared helpers ---------------------------- */

export function useLeaveTypes() {
  return useApi<unknown>("/api/leave/types");
}

export function normaliseTypes(value: unknown): LeaveType[] {
  const page = asPage<LeaveType>(value);
  if (page.items.length) return page.items;
  // Some builds return a plain object map of code → name
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return Object.entries(value as Record<string, unknown>).map(([code, raw]) =>
      typeof raw === "string"
        ? { code, name: raw }
        : { code, name: String(code), ...(typeof raw === "object" ? (raw as object) : {}) },
    ) as LeaveType[];
  }
  return [];
}

function typeSelectValue(type: LeaveType): string {
  return type.code || String(type.id ?? type.name);
}

function typeLabel(type: LeaveType): string {
  return `${type.name}${type.code ? ` (${type.code})` : ""}`;
}

/* ------------------------------ employee view ---------------------------- */

export function EmployeeLeave() {
  const toast = useToast();
  const year = currentYear();
  const balance = useApi<unknown>(`/api/leave/balance?year=${year}`);
  const types = useLeaveTypes();
  const requests = useApi<unknown>("/api/leave/requests?scope=me&page=1&page_size=50");

  const [leaveType, setLeaveType] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [cancelTarget, setCancelTarget] = useState<LeaveRequest | null>(null);
  const [cancelling, setCancelling] = useState(false);

  const typeList = normaliseTypes(types.data);
  const previewDays = useMemo(() => previewWorkingDays(start, end), [start, end]);
  // Default the select to the first available leave type until the user picks one.
  const selectedType = leaveType || (typeList.length ? typeSelectValue(typeList[0]) : "");

  const balanceItems = (balance.data as { items?: LeaveBalance["items"] } | undefined)?.items ??
    (Array.isArray(balance.data) ? (balance.data as LeaveBalance["items"]) : []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErrors({});
    setFormError(null);
    try {
      const created = await api<LeaveRequest>("/api/leave/requests", {
        method: "POST",
        body: {
          leave_type_code: selectedType,
          start_date: start,
          end_date: end,
          reason: reason.trim(),
        },
      });
      toast({
        type: "success",
        message: `Leave requested${created?.working_days ? ` · ${toNum(created.working_days)} working day(s)` : ""}.`,
      });
      setReason("");
      setStart("");
      setEnd("");
      balance.reload();
      requests.reload();
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors);
        setFormError(err.message);
      } else {
        setFormError(errorMessage(err));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const cancelRequest = async () => {
    if (!cancelTarget) return;
    setCancelling(true);
    try {
      await api(`/api/leave/requests/${cancelTarget.id}/cancel`, { method: "POST", body: {} });
      toast({ type: "success", message: "Request cancelled." });
      setCancelTarget(null);
      requests.reload();
      balance.reload();
    } catch (err) {
      toast({ type: "error", message: errorMessage(err) });
    } finally {
      setCancelling(false);
    }
  };

  const rows = asPage<LeaveRequest>(requests.data).items;

  return (
    <div className="space-y-6">
      <section aria-labelledby="balances-title">
        <h2 id="balances-title" className="text-lg font-semibold text-text">
          Leave balances
        </h2>
        <p className="mt-1 text-sm text-muted">{year} quota remaining after approved leave.</p>
        <div className="mt-4">
          {balance.loading && !balance.data && <StatsSkeleton count={4} />}
          {balance.error && !balance.loading && (
            <ErrorState message={balance.errorMessage} onRetry={balance.reload} />
          )}
          {balance.data !== undefined && (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {(balanceItems ?? []).map((item) => (
                <StatCard
                  key={item.code}
                  label={item.name || item.code}
                  value={`${toNum(item.remaining)} days`}
                  hint={`${toNum(item.used)} used · ${
                    item.quota === null || item.quota === undefined ? "unlimited" : `${toNum(item.quota)} quota`
                  }${toNum(item.pending) > 0 ? ` · ${toNum(item.pending)} pending` : ""}`}
                  tone={toNum(item.remaining) > 0 ? "ok" : "warn"}
                />
              ))}
              {(balanceItems ?? []).length === 0 && (
                <div className="sm:col-span-2 xl:col-span-4">
                  <EmptyState
                    title="No leave balances configured"
                    description="Your administrator defines leave types and quotas in Settings."
                  />
                </div>
              )}
            </div>
          )}
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-[420px,1fr]">
        <Card title="Request leave" description="Weekends are excluded; the server applies holidays.">
          <form onSubmit={submit} className="space-y-4" noValidate>
            {formError && (
              <div role="alert" className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
                {formError}
              </div>
            )}

            <Field label="Leave type" htmlFor="leave_type" error={errors.leave_type_code} required>
              <Select id="leave_type" value={selectedType} onChange={(e) => setLeaveType(e.target.value)} required>
                <option value="">Select a type…</option>
                {typeList.map((t) => (
                  <option key={typeSelectValue(t)} value={typeSelectValue(t)}>
                    {typeLabel(t)}
                  </option>
                ))}
              </Select>
            </Field>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Start date" htmlFor="leave_start" error={errors.start_date} required>
                <Input
                  id="leave_start"
                  type="date"
                  value={start}
                  min={todayISO()}
                  onChange={(e) => setStart(e.target.value)}
                  required
                />
              </Field>
              <Field label="End date" htmlFor="leave_end" error={errors.end_date} required>
                <Input
                  id="leave_end"
                  type="date"
                  value={end}
                  min={start || todayISO()}
                  onChange={(e) => setEnd(e.target.value)}
                  required
                />
              </Field>
            </div>

            <div className="rounded-lg border border-border bg-surface-2 px-3 py-2 text-xs text-muted">
              {previewDays === null ? (
                "Select both dates to preview working days."
              ) : (
                <>
                  Preview: <span className="font-semibold text-text">{previewDays}</span>{" "}
                  working day{previewDays === 1 ? "" : "s"} (weekends excluded — the server
                  recalculates with holidays).
                </>
              )}
            </div>

            <Field label="Reason" htmlFor="leave_reason" error={errors.reason} required>
              <Textarea
                id="leave_reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Family event"
                required
              />
            </Field>

            <Button type="submit" className="w-full" loading={submitting}>
              Submit request
            </Button>
          </form>
        </Card>

        <Card title="My requests" description="Cancel while a request is still pending.">
          {requests.loading && !requests.data && <ListSkeleton rows={4} />}
          {requests.error && !requests.loading && (
            <ErrorState message={requests.errorMessage} onRetry={requests.reload} />
          )}
          {requests.data !== undefined && rows.length === 0 && (
            <EmptyState title="No leave requests yet" description="Your requests will appear here." />
          )}
          {requests.data !== undefined && rows.length > 0 && (
            <div className="space-y-3">
              {rows.map((r) => (
                <div
                  key={r.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface-2 px-4 py-3"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-text">
                      {fmtDate(r.start_date)} → {fmtDate(r.end_date)}
                    </p>
                    <p className="text-xs text-muted">
                      {r.leave_type_code ?? "Leave"} · {toNum(r.working_days)} working day
                      {toNum(r.working_days) === 1 ? "" : "s"}
                      {r.reason ? ` · ${r.reason}` : ""}
                    </p>
                    {r.review_comment && (
                      <p className="mt-1 text-xs text-muted/80">Reviewer: {r.review_comment}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={String(r.status)} />
                    {String(r.status) === "pending" && (
                      <Button size="sm" variant="danger" onClick={() => setCancelTarget(r)}>
                        Cancel
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <ConfirmDialog
        open={cancelTarget !== null}
        title="Cancel leave request"
        message={
          cancelTarget
            ? `Cancel your leave from ${fmtDate(cancelTarget.start_date)} to ${fmtDate(cancelTarget.end_date)}?`
            : ""
        }
        confirmLabel="Cancel request"
        danger
        loading={cancelling}
        onConfirm={cancelRequest}
        onCancel={() => setCancelTarget(null)}
      />
    </div>
  );
}

/* -------------------------------- HR / Admin ------------------------------ */

export function HrLeave() {
  const toast = useToast();
  const { user } = useAuth();
  // Brief matrix #13: HR approves; Admin has view-only access to approvals.
  const canDecide = user?.role === "hr";
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [target, setTarget] = useState<LeaveRequest | null>(null);
  const [action, setAction] = useState<"approve" | "reject">("approve");
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);

  const path = `/api/leave/requests?scope=all&page=${page}&page_size=20${status ? `&status=${status}` : ""}`;
  const { data, loading, error, reload, errorMessage: listError } = useApi<unknown>(path);

  const rows = asPage<LeaveRequest>(data).items;
  const paging = asPage<LeaveRequest>(data);

  const decide = async () => {
    if (!target) return;
    setSaving(true);
    try {
      await api(`/api/leave/requests/${target.id}/${action}`, {
        method: "POST",
        body: { comment: comment.trim() || undefined },
      });
      toast({ type: "success", message: `Leave request ${action}d.` });
      setTarget(null);
      setComment("");
      reload();
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        toast({ type: "error", message: "You cannot review your own leave request." });
      } else {
        toast({ type: "error", message: errorMessage(err) });
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-text">Leave approvals</h2>
          <p className="mt-1 text-sm text-muted">
            All requests across your company.
            {!canDecide && " You have view-only access — HR approves requests."}
          </p>
        </div>
        <div className="flex items-end gap-3">
          <Field label="Filter by status" htmlFor="leave_status_filter" className="w-44">
            <Select
              id="leave_status_filter"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All statuses</option>
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
              <option value="cancelled">Cancelled</option>
            </Select>
          </Field>
          <Button variant="secondary" onClick={reload}>
            Refresh
          </Button>
        </div>
      </div>

      {loading && data === undefined && <ListSkeleton rows={5} />}
      {error && !loading && <ErrorState message={listError} onRetry={reload} />}
      {data !== undefined && rows.length === 0 && (
        <EmptyState
          title={status ? `No ${status} requests` : "No leave requests yet"}
          description="Requests submitted by employees will appear here."
        />
      )}

      {data !== undefined && rows.length > 0 && (
        <>
          <TableContainer>
            <Table>
              <thead>
                <TR>
                  <TH>Employee</TH>
                  <TH>Type</TH>
                  <TH>Dates</TH>
                  <TH align="right">Days</TH>
                  <TH>Reason</TH>
                  <TH>Status</TH>
                  <TH align="right">Actions</TH>
                </TR>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <TR key={r.id}>
                    <TD>
                      <span className="font-medium text-text">{r.employee_name ?? "—"}</span>
                      {r.employee_code && (
                        <span className="ml-2 font-mono text-xs text-muted">{r.employee_code}</span>
                      )}
                    </TD>
                    <TD>{r.leave_type_code ?? "—"}</TD>
                    <TD className="whitespace-nowrap text-muted">
                      {fmtDate(r.start_date)} → {fmtDate(r.end_date)}
                    </TD>
                    <TD align="right" className="tabular-nums">{toNum(r.working_days)}</TD>
                    <TD className="max-w-[18rem] truncate text-muted">
                      <span title={r.reason ?? undefined}>{r.reason || "—"}</span>
                    </TD>
                    <TD>
                      <StatusBadge status={String(r.status)} />
                    </TD>
                    <TD align="right">
                      {String(r.status) === "pending" ? (
                        canDecide ? (
                          <span className="flex justify-end gap-2">
                            <Button
                              size="sm"
                              variant="success"
                              onClick={() => {
                                setTarget(r);
                                setAction("approve");
                                setComment("");
                              }}
                            >
                              Approve
                            </Button>
                            <Button
                              size="sm"
                              variant="danger"
                              onClick={() => {
                                setTarget(r);
                                setAction("reject");
                                setComment("");
                              }}
                            >
                              Reject
                            </Button>
                          </span>
                        ) : (
                          <span className="text-xs font-medium text-muted">View only</span>
                        )
                      ) : (
                        <span className="text-xs text-muted">—</span>
                      )}
                    </TD>
                  </TR>
                ))}
              </tbody>
            </Table>
            <Pagination page={paging.page} pageSize={paging.page_size} total={paging.total} onPage={setPage} />
          </TableContainer>
        </>
      )}

      <Modal
        open={target !== null}
        onClose={() => setTarget(null)}
        title={action === "approve" ? "Approve leave" : "Reject leave"}
        description={
          target
            ? `${target.employee_name ?? "Employee"} · ${fmtDate(target.start_date)} → ${fmtDate(target.end_date)}`
            : undefined
        }
        footer={
          <>
            <Button variant="secondary" onClick={() => setTarget(null)} disabled={saving}>
              Cancel
            </Button>
            <Button variant={action === "approve" ? "primary" : "danger"} onClick={decide} loading={saving}>
              {action === "approve" ? "Approve" : "Reject"}
            </Button>
          </>
        }
      >
        <Field label="Comment (optional)" htmlFor="leave_comment" hint="The employee is notified with this text.">
          <Textarea
            id="leave_comment"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder={action === "approve" ? "Approved — enjoy." : "Peak season, please pick another week."}
          />
        </Field>
      </Modal>
    </div>
  );
}
