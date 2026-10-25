"use client";

import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/components/auth/Auth";
import { useApi } from "@/hooks/useApi";
import { asPage, asRows, isObject, pick, toNum, toStr } from "@/lib/utils";
import { fmtDate, fmtHours, fmtTime, todayISO } from "@/lib/format";
import type { Correction } from "@/types/api";
import { Card, StatCard } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/Badge";
import { Field, Input, Select, Textarea } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { ErrorState, EmptyState } from "@/components/ui/States";
import { TableSkeleton, ListSkeleton } from "@/components/ui/Skeleton";
import { TableContainer, Table, TH, TD, TR, Pagination } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";

interface BoardRow {
  id: string;
  code: string;
  name: string;
  department: string;
  designation: string;
  status: string;
  check_in: string;
  check_out: string;
  hours: number;
}

function normaliseBoard(value: unknown): BoardRow[] {
  const source = isObject(value) ? (value.records ?? value.items ?? value.rows ?? value) : value;
  return asRows(source).map((r, i) => ({
    id: `${toStr(pick(r, ["date"]), "")}-${i}`,
    code: toStr(pick(r, ["employee_code", "code"]), "—"),
    name: toStr(pick(r, ["employee_name", "full_name", "name", "first_name"]), "—"),
    department: toStr(pick(r, ["department", "department_name"]), "—"),
    designation: toStr(pick(r, ["designation"]), "—"),
    status: toStr(pick(r, ["status"]), "absent"),
    check_in: toStr(pick(r, ["check_in", "in"]), ""),
    check_out: toStr(pick(r, ["check_out", "out"]), ""),
    hours: toNum(pick(r, ["worked_hours", "hours"]), 0),
  }));
}

type Tab = "board" | "corrections";

export function HrAttendance() {
  const [tab, setTab] = useState<Tab>("board");
  const [date, setDate] = useState(todayISO());
  const [departmentId, setDepartmentId] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const departments = useApi<unknown>("/api/org/departments");
  const boardPath = `/api/attendance/board?date=${date}${departmentId ? `&department_id=${departmentId}` : ""}`;
  const board = useApi<unknown>(tab === "board" ? boardPath : null);

  const rows = normaliseBoard(board.data);
  const filtered = statusFilter ? rows.filter((r) => r.status === statusFilter) : rows;
  const departmentRows = asRows(departments.data);

  const counts = rows.reduce<Record<string, number>>((acc, r) => {
    acc[r.status] = (acc[r.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2 border-b border-border" role="tablist">
        {(
          [
            ["board", "Day board"],
            ["corrections", "Pending corrections"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 px-4 py-2.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
              tab === key ? "border-accent text-text" : "border-transparent text-muted hover:text-text"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "board" && (
        <>
          <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-4 sm:flex-row sm:items-end">
            <Field label="Date" htmlFor="board_date" className="sm:w-48">
              <Input id="board_date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </Field>
            <Field label="Department" htmlFor="board_dept" className="sm:w-52">
              <Select id="board_dept" value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}>
                <option value="">All departments</option>
                {departmentRows.map((d) => (
                  <option key={String(d.id)} value={String(d.id)}>
                    {toStr(d, String(d.id))}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Status" htmlFor="board_status" className="sm:w-44">
              <Select id="board_status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="">All statuses</option>
                {["present", "late", "half_day", "absent", "on_leave", "missing_checkout", "weekend", "holiday"].map(
                  (s) => (
                    <option key={s} value={s}>
                      {s.replace(/_/g, " ")}
                    </option>
                  ),
                )}
              </Select>
            </Field>
          </div>

          {!board.loading && board.data !== undefined && !board.error && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-6">
              <StatCard label="Roster" value={String(rows.length)} />
              {Object.entries(counts).slice(0, 5).map(([status, count]) => (
                <StatCard
                  key={status}
                  label={status.replace(/_/g, " ")}
                  value={String(count)}
                  tone={status === "present" ? "ok" : status === "absent" ? "danger" : "warn"}
                />
              ))}
            </div>
          )}

          {board.loading && !board.data && <TableSkeleton rows={8} cols={6} />}
          {board.error && !board.loading && <ErrorState message={board.errorMessage} onRetry={board.reload} />}

          {board.data !== undefined && !board.loading && (
            <>
              {filtered.length === 0 ? (
                <EmptyState
                  title={`No attendance records for ${fmtDate(date)}`}
                  description={
                    statusFilter
                      ? "No employees match this status filter."
                      : "Employees appear here once they check in, or the roster has not been generated for this date."
                  }
                />
              ) : (
                <TableContainer>
                  <Table>
                    <thead>
                      <TR>
                        <TH>Code</TH>
                        <TH>Employee</TH>
                        <TH>Department</TH>
                        <TH>Designation</TH>
                        <TH>Status</TH>
                        <TH align="right">In</TH>
                        <TH align="right">Out</TH>
                        <TH align="right">Hours</TH>
                      </TR>
                    </thead>
                    <tbody>
                      {filtered.map((row) => (
                        <TR key={row.id}>
                          <TD className="font-mono text-xs text-muted">{row.code}</TD>
                          <TD className="font-medium text-text">{row.name}</TD>
                          <TD className="text-muted">{row.department}</TD>
                          <TD className="text-muted">{row.designation}</TD>
                          <TD>
                            <StatusBadge status={row.status} />
                          </TD>
                          <TD align="right" className="tabular-nums">{fmtTime(row.check_in)}</TD>
                          <TD align="right" className="tabular-nums">{fmtTime(row.check_out)}</TD>
                          <TD align="right" className="tabular-nums">{fmtHours(row.hours)}</TD>
                        </TR>
                      ))}
                    </tbody>
                  </Table>
                </TableContainer>
              )}
            </>
          )}
        </>
      )}

      {tab === "corrections" && <CorrectionsInbox />}
    </div>
  );
}

function CorrectionsInbox() {
  const toast = useToast();
  const { user } = useAuth();
  // Brief matrix #11: HR decides corrections; Admin has view-only access.
  const canDecide = user?.role === "hr";
  const [page, setPage] = useState(1);
  const path = `/api/attendance/corrections?status=pending&scope=all&page=${page}&page_size=20`;
  const { data, loading, error, reload, errorMessage: listError } = useApi<unknown>(path);
  const [target, setTarget] = useState<Correction | null>(null);
  const [action, setAction] = useState<"approve" | "reject">("approve");
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);

  const rows = asPage<Correction>(data).items;

  const decide = async () => {
    if (!target) return;
    setSaving(true);
    try {
      await api(`/api/attendance/corrections/${target.id}/${action}`, {
        method: "POST",
        body: { comment: comment.trim() || undefined },
      });
      toast({
        type: "success",
        message: `Correction ${action === "approve" ? "approved" : "rejected"}.`,
      });
      setTarget(null);
      setComment("");
      reload();
    } catch (err) {
      toast({ type: "error", message: errorMessage(err) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      {loading && data === undefined && <ListSkeleton rows={4} />}
      {error && !loading && <ErrorState message={listError} onRetry={reload} />}
      {data !== undefined && !loading && rows.length === 0 && (
        <EmptyState title="No pending corrections" description="All correction requests have been reviewed." />
      )}
      {data !== undefined && rows.length > 0 && (
        <>
          <div className="space-y-3">
            {rows.map((c) => (
              <Card key={c.id} className="p-0">
                <div className="flex flex-wrap items-start justify-between gap-4 p-5">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold text-text">
                        {c.employee_name ?? "Employee"}
                        {c.employee_code ? ` · ${c.employee_code}` : ""}
                      </p>
                      <StatusBadge status={c.status} />
                    </div>
                    <p className="mt-1 text-xs text-muted">
                      {fmtDate(c.attendance_date)} · {fmtTime(c.requested_check_in)} →{" "}
                      {fmtTime(c.requested_check_out)}
                    </p>
                    <p className="mt-2 text-sm text-text/80">{c.reason}</p>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    {canDecide ? (
                      <>
                        <Button
                          variant="success"
                          onClick={() => {
                            setTarget(c);
                            setAction("approve");
                            setComment("");
                          }}
                        >
                          Approve
                        </Button>
                        <Button
                          variant="danger"
                          onClick={() => {
                            setTarget(c);
                            setAction("reject");
                            setComment("");
                          }}
                        >
                          Reject
                        </Button>
                      </>
                    ) : (
                      <span className="text-xs font-medium text-muted">View only</span>
                    )}
                  </div>
                </div>
              </Card>
            ))}
          </div>
          {asPage<Correction>(data).total > asPage<Correction>(data).page_size && (
            <Pagination
              page={asPage<Correction>(data).page}
              pageSize={asPage<Correction>(data).page_size}
              total={asPage<Correction>(data).total}
              onPage={setPage}
            />
          )}
        </>
      )}

      <Modal
        open={target !== null}
        onClose={() => setTarget(null)}
        title={action === "approve" ? "Approve correction" : "Reject correction"}
        description={
          target
            ? `${target.employee_name ?? "Employee"} · ${fmtDate(target.attendance_date)}`
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
        <Field label="Comment (optional)" htmlFor="decision_comment" hint="Visible to the employee.">
          <Textarea
            id="decision_comment"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder={action === "approve" ? "Looks correct." : "Please provide proof of working hours."}
          />
        </Field>
      </Modal>
    </div>
  );
}
