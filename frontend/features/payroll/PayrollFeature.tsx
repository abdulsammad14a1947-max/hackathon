"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { asPage, toNum, toStr, pick } from "@/lib/utils";
import { fmtDate, fmtDateTime, fmtMoney, currentYear, monthName, MONTHS } from "@/lib/format";
import type { Employee, PayrollRun, SalaryStructure } from "@/types/api";
import { StatCard } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/Badge";
import { Field, Input, Select } from "@/components/ui/Field";
import { Modal, ConfirmDialog } from "@/components/ui/Modal";
import { ErrorState, EmptyState } from "@/components/ui/States";
import { ListSkeleton, TableSkeleton, StatsSkeleton } from "@/components/ui/Skeleton";
import { Pagination, TableContainer, Table, TH, TD, TR } from "@/components/ui/Table";
import { useToast } from "@/components/ui/Toast";
import { Icon } from "@/components/layout/Icon";
import { useAuth } from "@/components/auth/Auth";

/* ----------------------------- salary structures ------------------------- */

function AddSalaryStructureModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const toast = useToast();
  const employees = useApi<unknown>(open ? "/api/employees?page=1&page_size=100" : null);
  const [employeeId, setEmployeeId] = useState("");
  const [basic, setBasic] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [effectiveTo, setEffectiveTo] = useState("");
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const employeeRows = asPage<Employee>(employees.data).items;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setErrors({});
    setFormError(null);
    try {
      await api("/api/payroll/salary-structures", {
        method: "POST",
        body: {
          employee_id: Number(employeeId),
          basic_salary: Number(basic),
          effective_from: effectiveFrom,
          effective_to: effectiveTo || null,
        },
      });
      toast({ type: "success", message: "Salary structure added." });
      onCreated();
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

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Add salary structure"
      description="Historical structures keep payroll history intact."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" form="salary-structure-form" loading={saving}>
            Save
          </Button>
        </>
      }
    >
      <form id="salary-structure-form" onSubmit={submit} className="space-y-4" noValidate>
        {formError && (
          <div role="alert" className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
            {formError}
          </div>
        )}
        <Field label="Employee" htmlFor="ss_employee" error={errors.employee_id} required>
          <Select id="ss_employee" value={employeeId} onChange={(e) => setEmployeeId(e.target.value)} required>
            <option value="">Select employee…</option>
            {employeeRows.map((emp) => (
              <option key={emp.id} value={String(emp.id)}>
                {emp.employee_code} — {emp.full_name ?? `${emp.first_name} ${emp.last_name}`}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Basic salary (PKR)" htmlFor="ss_basic" error={errors.basic_salary} required>
          <Input id="ss_basic" type="number" min="0" step="0.01" value={basic} onChange={(e) => setBasic(e.target.value)} required />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Effective from" htmlFor="ss_from" error={errors.effective_from} required>
            <Input id="ss_from" type="date" value={effectiveFrom} onChange={(e) => setEffectiveFrom(e.target.value)} required />
          </Field>
          <Field label="Effective to (optional)" htmlFor="ss_to" error={errors.effective_to}>
            <Input id="ss_to" type="date" value={effectiveTo} onChange={(e) => setEffectiveTo(e.target.value)} />
          </Field>
        </div>
      </form>
    </Modal>
  );
}

function GenerateRunModal({
  open,
  onClose,
  onGenerated,
}: {
  open: boolean;
  onClose: () => void;
  onGenerated: (run?: PayrollRun) => void;
}) {
  const toast = useToast();
  const [year, setYear] = useState(currentYear());
  const [month, setMonth] = useState(new Date().getMonth() + 1);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      const run = await api<PayrollRun>("/api/payroll/runs", {
        method: "POST",
        body: { year: Number(year), month: Number(month) },
      });
      toast({ type: "success", message: `${monthName(Number(month))} ${year} draft generated.` });
      onGenerated(run);
      onClose();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Generate payroll draft"
      description="Regenerating an existing draft replaces its items."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" form="generate-run-form" loading={saving}>
            Generate draft
          </Button>
        </>
      }
    >
      <form id="generate-run-form" onSubmit={submit} className="space-y-4" noValidate>
        {formError && (
          <div role="alert" className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
            {formError}
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Year" htmlFor="run_year" required>
            <Input
              id="run_year"
              type="number"
              min="2000"
              max="2100"
              value={year}
              onChange={(e) => setYear(Number(e.target.value))}
              required
            />
          </Field>
          <Field label="Month" htmlFor="run_month" required>
            <Select id="run_month" value={month} onChange={(e) => setMonth(Number(e.target.value))}>
              {MONTHS.map((name, i) => (
                <option key={name} value={i + 1}>
                  {name}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <p className="text-xs text-muted">
          Drafts are recalculated from attendance, leave and salary structures. Only an
          administrator can finalize a run.
        </p>
      </form>
    </Modal>
  );
}

/* --------------------------------- page ---------------------------------- */

export function PayrollIndex() {
  const router = useRouter();
  const { user } = useAuth();
  // Brief matrix #14-#15: HR manages structures and drafts; Admin is view-only.
  const canManage = user?.role === "hr";
  const [salaryPage, setSalaryPage] = useState(1);
  const [runPage, setRunPage] = useState(1);
  const [addSalaryOpen, setAddSalaryOpen] = useState(false);
  const [generateOpen, setGenerateOpen] = useState(false);

  const structures = useApi<unknown>(`/api/payroll/salary-structures?page=${salaryPage}&page_size=10`);
  const runs = useApi<unknown>(`/api/payroll/runs?page=${runPage}&page_size=20`);

  const structureRows = asPage<SalaryStructure>(structures.data).items;
  const runRows = asPage<PayrollRun>(runs.data).items;

  const structurePaging = asPage<SalaryStructure>(structures.data);
  const runPaging = asPage<PayrollRun>(runs.data);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-text">Payroll</h2>
          <p className="mt-1 text-sm text-muted">
            Salary structures feed the monthly draft → review → finalize workflow.
          </p>
        </div>
        {canManage ? (
          <Button onClick={() => setGenerateOpen(true)}>
            <Icon name="plus" className="h-4 w-4" /> Generate draft
          </Button>
        ) : (
          <span className="text-xs font-medium text-muted">View only — HR generates drafts</span>
        )}
      </div>

      {/* Runs */}
      <section aria-labelledby="runs-title" className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 id="runs-title" className="text-sm font-semibold uppercase tracking-wider text-muted">
            Payroll runs
          </h3>
        </div>

        {runs.loading && runs.data === undefined && <TableSkeleton rows={5} cols={6} />}
        {runs.error && !runs.loading && (
          <ErrorState message={runs.errorMessage} onRetry={runs.reload} />
        )}
        {runs.data !== undefined && runRows.length === 0 && (
          <EmptyState
            title="No payroll runs yet"
            description="Generate a draft for a month to calculate salaries from attendance and leave."
            action={
              canManage ? (
                <Button onClick={() => setGenerateOpen(true)}>Generate draft</Button>
              ) : undefined
            }
          />
        )}
        {runRows.length > 0 && (
          <TableContainer>
            <Table>
              <thead>
                <TR>
                  <TH>Period</TH>
                  <TH>Status</TH>
                  <TH align="right">Gross</TH>
                  <TH align="right">Deductions</TH>
                  <TH align="right">Net pay</TH>
                  <TH>Generated</TH>
                  <TH align="right"> </TH>
                </TR>
              </thead>
              <tbody>
                {runRows.map((run) => (
                  <TR key={run.id} onClick={() => router.push(`/payroll/${run.id}`)}>
                    <TD className="font-medium text-text">
                      {monthName(toNum(run.period_month, 1))} {run.period_year}
                    </TD>
                    <TD>
                      <StatusBadge status={run.status} />
                    </TD>
                    <TD align="right">{fmtMoney(run.total_gross)}</TD>
                    <TD align="right">{fmtMoney(run.total_deductions)}</TD>
                    <TD align="right" className="font-semibold">{fmtMoney(run.total_net)}</TD>
                    <TD className="text-muted">{fmtDateTime(run.generated_at)}</TD>
                    <TD align="right">
                      <span className="text-xs text-accent">Open →</span>
                    </TD>
                  </TR>
                ))}
              </tbody>
            </Table>
            <Pagination
              page={runPaging.page}
              pageSize={runPaging.page_size}
              total={runPaging.total}
              onPage={setRunPage}
            />
          </TableContainer>
        )}
      </section>

      {/* Salary structures */}
      <section aria-labelledby="structures-title" className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 id="structures-title" className="text-sm font-semibold uppercase tracking-wider text-muted">
            Salary structures
          </h3>
          {canManage ? (
            <Button variant="secondary" onClick={() => setAddSalaryOpen(true)}>
              <Icon name="plus" className="h-4 w-4" /> Add structure
            </Button>
          ) : (
            <span className="text-xs font-medium text-muted">View only</span>
          )}
        </div>

        {structures.loading && structures.data === undefined && <ListSkeleton rows={3} />}
        {structures.error && !structures.loading && (
          <ErrorState message={structures.errorMessage} onRetry={structures.reload} />
        )}
        {structures.data !== undefined && structureRows.length === 0 && (
          <EmptyState
            title="No salary structures"
            description="Add a structure per employee — payroll cannot run without one."
            action={
              canManage ? (
                <Button variant="secondary" onClick={() => setAddSalaryOpen(true)}>
                  Add structure
                </Button>
              ) : undefined
            }
          />
        )}
        {structureRows.length > 0 && (
          <TableContainer>
            <Table>
              <thead>
                <TR>
                  <TH>Employee</TH>
                  <TH align="right">Basic salary</TH>
                  <TH>Effective from</TH>
                  <TH>Effective to</TH>
                </TR>
              </thead>
              <tbody>
                {structureRows.map((s) => (
                  <TR key={s.id} onClick={() => router.push(`/employees/${s.employee_id}`)}>
                    <TD>
                      <span className="font-medium text-text">
                        {s.employee_name ?? `Employee #${s.employee_id}`}
                      </span>
                      {s.employee_code && (
                        <span className="ml-2 font-mono text-xs text-muted">{s.employee_code}</span>
                      )}
                    </TD>
                    <TD align="right" className="font-semibold">{fmtMoney(s.basic_salary)}</TD>
                    <TD className="text-muted">{fmtDate(s.effective_from)}</TD>
                    <TD className="text-muted">{s.effective_to ? fmtDate(s.effective_to) : "Current"}</TD>
                  </TR>
                ))}
              </tbody>
            </Table>
            <Pagination
              page={structurePaging.page}
              pageSize={structurePaging.page_size}
              total={structurePaging.total}
              onPage={setSalaryPage}
            />
          </TableContainer>
        )}
      </section>

      <AddSalaryStructureModal
        open={addSalaryOpen}
        onClose={() => setAddSalaryOpen(false)}
        onCreated={() => structures.reload()}
      />
      <GenerateRunModal
        open={generateOpen}
        onClose={() => setGenerateOpen(false)}
        onGenerated={(run) => {
          runs.reload();
          if (run && toNum(run.id, 0) > 0) router.push(`/payroll/${run.id}`);
        }}
      />
    </div>
  );
}

/* ------------------------------- run detail ------------------------------ */

export function PayrollRunDetail({ runId }: { runId: number }) {
  const router = useRouter();
  const toast = useToast();
  const { user } = useAuth();
  const { data, loading, error, reload, errorMessage: loadError } = useApi<unknown>(
    `/api/payroll/runs/${runId}`,
  );
  const items = useApi<unknown>(`/api/payroll/runs/${runId}/items`);
  const [dialog, setDialog] = useState<null | "regenerate" | "finalize">(null);
  const [busy, setBusy] = useState(false);

  const run = (data ?? null) as PayrollRun | { run?: PayrollRun } | null;
  const runRow: PayrollRun | null =
    run && typeof run === "object" && "run" in run && run.run ? run.run : (run as PayrollRun | null);
  const status = String(runRow?.status ?? "").toLowerCase();
  const isFinalized = status === "finalized";
  const canFinalize = user?.role === "admin";
  // Brief matrix #15: HR creates/regenerates drafts; Admin is view-only until finalize.
  const canRegenerate = user?.role === "hr";

  const itemRows = asPage<Record<string, unknown>>(items.data).items;

  const regenerate = async () => {
    if (!runRow) return;
    setBusy(true);
    try {
      await api("/api/payroll/runs", {
        method: "POST",
        body: { year: runRow.period_year, month: runRow.period_month },
      });
      toast({ type: "success", message: "Draft regenerated." });
      reload();
      items.reload();
    } catch (err) {
      toast({ type: "error", message: errorMessage(err) });
    } finally {
      setBusy(false);
      setDialog(null);
    }
  };

  const finalize = async () => {
    setBusy(true);
    try {
      await api(`/api/payroll/runs/${runId}/finalize`, { method: "POST", body: {} });
      toast({ type: "success", message: "Payroll run finalized and locked." });
      reload();
      items.reload();
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        toast({ type: "error", message: "Only administrators can finalize a payroll run." });
      } else {
        toast({ type: "error", message: errorMessage(err) });
      }
    } finally {
      setBusy(false);
      setDialog(null);
    }
  };

  if (error) {
    return <ErrorState message={loadError} onRetry={reload} />;
  }
  if (loading || !runRow) {
    return (
      <div className="space-y-4">
        <StatsSkeleton count={4} />
        <TableSkeleton rows={6} cols={8} />
      </div>
    );
  }

  const period = `${monthName(runRow.period_month)} ${runRow.period_year}`;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <button
            onClick={() => router.push("/payroll")}
            className="text-xs font-medium text-accent hover:text-accent-hover"
          >
            ← Back to payroll
          </button>
          <h2 className="mt-1 text-xl font-semibold tracking-tight text-text">{period}</h2>
          <p className="text-sm text-muted">
            Generated {fmtDateTime(runRow.generated_at)}
            {runRow.finalized_at ? ` · finalized ${fmtDateTime(runRow.finalized_at)}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={runRow.status} />
          {isFinalized && (
            <span className="rounded-full border border-border-strong bg-surface-3 px-3 py-1 text-xs font-medium text-muted">
              Read-only — finalized
            </span>
          )}
          {!isFinalized && (
            <>
              {canRegenerate && (
                <Button variant="secondary" onClick={() => setDialog("regenerate")}>
                  Regenerate draft
                </Button>
              )}
              {canFinalize && (
                <Button variant="success" onClick={() => setDialog("finalize")}>
                  Finalize run
                </Button>
              )}
              {!canRegenerate && !canFinalize && (
                <span className="text-xs font-medium text-muted">View only</span>
              )}
            </>
          )}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Total gross" value={fmtMoney(runRow.total_gross)} />
        <StatCard label="Total deductions" value={fmtMoney(runRow.total_deductions)} tone="warn" />
        <StatCard label="Total net pay" value={fmtMoney(runRow.total_net)} tone="ok" />
      </div>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted">Items</h3>
        {items.loading && items.data === undefined && <TableSkeleton rows={6} cols={9} />}
        {items.error && !items.loading && (
          <ErrorState message={items.errorMessage} onRetry={items.reload} />
        )}
        {items.data !== undefined && itemRows.length === 0 && (
          <EmptyState
            title="No payroll items"
            description="Regenerate the draft — items are created from active employees with a salary structure."
          />
        )}
        {itemRows.length > 0 && (
          <TableContainer>
            <Table>
              <thead>
                <TR>
                  <TH>Employee</TH>
                  <TH align="right">Basic</TH>
                  <TH align="right">HRA</TH>
                  <TH align="right">Medical</TH>
                  <TH align="right">Gross</TH>
                  <TH align="right">Working</TH>
                  <TH align="right">Present</TH>
                  <TH align="right">Absent</TH>
                  <TH align="right">Unpaid</TH>
                  <TH align="right">Half</TH>
                  <TH align="right">Deduction</TH>
                  <TH align="right">Tax</TH>
                  <TH align="right">Net pay</TH>
                  <TH>Note</TH>
                </TR>
              </thead>
              <tbody>
                {itemRows.map((raw, i) => {
                  const row = raw as Record<string, unknown>;
                  return (
                    <TR key={toNum(row.id, i)}>
                      <TD>
                        <span className="font-medium text-text">
                          {toStr(pick(row, ["employee_name", "full_name"]), `Employee #${row.employee_id}`)}
                        </span>
                        {Boolean(row.employee_code) && (
                          <span className="ml-2 font-mono text-xs text-muted">{String(row.employee_code)}</span>
                        )}
                      </TD>
                      <TD align="right">{fmtMoney(toNum(row.basic))}</TD>
                      <TD align="right">{fmtMoney(toNum(row.hra))}</TD>
                      <TD align="right">{fmtMoney(toNum(row.medical))}</TD>
                      <TD align="right" className="font-medium">{fmtMoney(toNum(row.gross))}</TD>
                      <TD align="right">{toNum(row.working_days)}</TD>
                      <TD align="right">{toNum(row.present_days)}</TD>
                      <TD align="right">{toNum(row.absent_days)}</TD>
                      <TD align="right">{toNum(row.unpaid_leave_days)}</TD>
                      <TD align="right">{toNum(row.half_days)}</TD>
                      <TD align="right">{fmtMoney(toNum(row.deduction_amount))}</TD>
                      <TD align="right">{fmtMoney(toNum(row.tax))}</TD>
                      <TD align="right" className="font-semibold text-success">
                        {fmtMoney(toNum(row.net_pay))}
                      </TD>
                      <TD className="text-xs text-muted">{toStr(row.note, "—")}</TD>
                    </TR>
                  );
                })}
              </tbody>
            </Table>
          </TableContainer>
        )}
      </section>

      <ConfirmDialog
        open={dialog === "regenerate"}
        title="Regenerate this draft?"
        message={`Every item for ${period} will be recalculated from attendance, leave and salary structures, replacing the current draft.`}
        confirmLabel="Regenerate"
        loading={busy}
        onConfirm={regenerate}
        onCancel={() => setDialog(null)}
      />

      <ConfirmDialog
        open={dialog === "finalize"}
        title="Finalize payroll run?"
        message={`${period} will become immutable (read-only) and payslips become available. This action is audit-logged and cannot be undone.`}
        confirmLabel="Finalize"
        loading={busy}
        onConfirm={finalize}
        onCancel={() => setDialog(null)}
      >
        <div className="mt-3 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">
          Administrator action — HR users cannot finalize runs.
        </div>
      </ConfirmDialog>
    </div>
  );
}

