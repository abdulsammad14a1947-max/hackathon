"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth, RequireRole } from "@/components/auth/Auth";
import { useApi } from "@/hooks/useApi";
import { useDebounced } from "@/hooks/useDebounced";
import { downloadFile, errorMessage } from "@/lib/api";
import { asRows, toStr, cx } from "@/lib/utils";
import { fmtDate } from "@/lib/format";
import type { Employee, Paginated } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select } from "@/components/ui/Field";
import { StatusBadge } from "@/components/ui/Badge";
import { ErrorState, EmptyState } from "@/components/ui/States";
import { TableSkeleton, PageSkeleton } from "@/components/ui/Skeleton";
import { TableContainer, Table, TH, TD, TR, Pagination } from "@/components/ui/Table";
import { Icon } from "@/components/layout/Icon";
import { useToast } from "@/components/ui/Toast";
import { AddEmployeeModal } from "@/features/employees/AddEmployeeModal";
import { ImportEmployeesModal } from "@/features/employees/ImportEmployeesModal";

function EmployeeDirectory() {
  const router = useRouter();
  const { user } = useAuth();
  const toast = useToast();

  const [q, setQ] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [addOpen, setAddOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  // Brief matrix #06/#08: HR registers, imports and exports employees; Admin is view-only.
  const canManage = user?.role === "hr";

  const debouncedQ = useDebounced(q, 350);

  useEffect(() => {
    if (user?.role === "employee") {
      router.replace(user.employee_id ? `/employees/${user.employee_id}` : "/dashboard");
    }
  }, [user, router]);

  const departments = useApi<unknown>("/api/org/departments");

  const query = useMemo(() => {
    const params = new URLSearchParams();
    if (debouncedQ.trim()) params.set("q", debouncedQ.trim());
    if (departmentId) params.set("department_id", departmentId);
    if (status) params.set("status", status);
    params.set("page", String(page));
    params.set("page_size", String(pageSize));
    return `/api/employees?${params.toString()}`;
  }, [debouncedQ, departmentId, status, page, pageSize]);

  const { data, loading, error, reload, errorMessage: listError } = useApi<Paginated<Employee>>(query);

  const rows = data?.items ?? [];
  const departmentOptions = asRows(departments.data);

  const exportCsv = async () => {
    setExporting(true);
    try {
      await downloadFile("/api/employees/export", "employees.csv");
      toast({ type: "success", message: "Employee CSV exported." });
    } catch (err) {
      toast({ type: "error", message: errorMessage(err) });
    } finally {
      setExporting(false);
    }
  };

  if (user?.role === "employee") return <PageSkeleton />;

  const hasFilters = Boolean(debouncedQ.trim() || departmentId || status);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-text">Employee directory</h2>
          <p className="mt-1 text-sm text-muted">
            {data ? `${data.total} employee${data.total === 1 ? "" : "s"} · page ${data.page}` : "Search, filter and manage people."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canManage ? (
            <>
              <Button variant="secondary" onClick={exportCsv} loading={exporting}>
                <Icon name="download" className="h-4 w-4" /> Export CSV
              </Button>
              <Button variant="secondary" onClick={() => setImportOpen(true)}>
                <Icon name="upload" className="h-4 w-4" /> Import
              </Button>
              <Button onClick={() => setAddOpen(true)}>
                <Icon name="plus" className="h-4 w-4" /> Add employee
              </Button>
            </>
          ) : (
            <span className="self-center text-xs font-medium text-muted">
              View only — HR manages employee records
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-4 sm:flex-row sm:items-end">
        <Field label="Search" htmlFor="emp_search" className="flex-1">
          <div className="relative">
            <Icon
              name="search"
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
            />
            <Input
              id="emp_search"
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(1);
              }}
              placeholder="Name, code or email…"
              className="pl-9"
            />
          </div>
        </Field>
        <Field label="Department" htmlFor="emp_dept" className="sm:w-52">
          <Select
            id="emp_dept"
            value={departmentId}
            onChange={(e) => {
              setDepartmentId(e.target.value);
              setPage(1);
            }}
          >
            <option value="">All departments</option>
            {departmentOptions.map((d) => (
              <option key={String(d.id)} value={String(d.id)}>
                {toStr(d, String(d.id))}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Status" htmlFor="emp_status" className="sm:w-44">
          <Select
            id="emp_status"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="terminated">Terminated</option>
          </Select>
        </Field>
        {hasFilters && (
          <Button
            variant="ghost"
            onClick={() => {
              setQ("");
              setDepartmentId("");
              setStatus("");
              setPage(1);
            }}
          >
            Clear
          </Button>
        )}
      </div>

      {loading && !data && <TableSkeleton rows={8} cols={7} />}

      {error && !loading && <ErrorState message={listError} onRetry={reload} />}

      {data && !loading && rows.length === 0 && (
        <EmptyState
          title={hasFilters ? "No employees match these filters" : "No employees yet"}
          description={
            hasFilters
              ? "Try a different search term or clear the filters."
              : "Add your first employee manually or import a CSV file."
          }
          action={
            hasFilters ? (
              <Button
                variant="secondary"
                onClick={() => {
                  setQ("");
                  setDepartmentId("");
                  setStatus("");
                }}
              >
                Clear filters
              </Button>
            ) : canManage ? (
              <Button onClick={() => setAddOpen(true)}>Add employee</Button>
            ) : undefined
          }
        />
      )}

      {data && rows.length > 0 && (
        <div className={cx(loading && "opacity-60 transition-opacity")}>
          <TableContainer>
            <Table>
              <thead>
                <TR>
                  <TH>Code</TH>
                  <TH>Name</TH>
                  <TH>Email</TH>
                  <TH>Department</TH>
                  <TH>Designation</TH>
                  <TH>Joined</TH>
                  <TH>Status</TH>
                </TR>
              </thead>
              <tbody>
                {rows.map((emp) => (
                  <TR
                    key={emp.id}
                    onClick={() => router.push(`/employees/${emp.id}`)}
                    className="focus-visible:ring-1 focus-visible:ring-accent"
                  >
                    <TD className="font-mono text-xs text-muted">{emp.employee_code}</TD>
                    <TD>
                      <span className="flex items-center gap-2.5">
                        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-surface-3 text-[11px] font-semibold text-muted">
                          {(emp.full_name ?? `${emp.first_name} ${emp.last_name}`)
                            .split(/\s+/)
                            .filter(Boolean)
                            .slice(0, 2)
                            .map((p: string) => p[0])
                            .join("")
                            .toUpperCase()}
                        </span>
                        <span className="font-medium text-text">
                          {emp.full_name ?? `${emp.first_name} ${emp.last_name}`}
                        </span>
                      </span>
                    </TD>
                    <TD className="text-muted">{emp.email}</TD>
                    <TD>{toStr(emp.department, "—")}</TD>
                    <TD>{toStr(emp.designation, "—")}</TD>
                    <TD className="tabular-nums text-muted">{fmtDate(emp.joining_date)}</TD>
                    <TD>
                      <StatusBadge status={String(emp.employment_status ?? "active")} />
                    </TD>
                  </TR>
                ))}
              </tbody>
            </Table>
            <Pagination
              page={data.page}
              pageSize={data.page_size}
              total={data.total}
              onPage={setPage}
              onPageSize={(size) => {
                setPageSize(size);
                setPage(1);
              }}
            />
          </TableContainer>
        </div>
      )}

      <AddEmployeeModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onCreated={() => reload()}
      />
      <ImportEmployeesModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={() => reload()}
      />
    </div>
  );
}

export default function EmployeesPage() {
  return (
    <RequireRole roles={["admin", "hr"]}>
      <EmployeeDirectory />
    </RequireRole>
  );
}
