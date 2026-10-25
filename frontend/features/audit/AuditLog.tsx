"use client";

import { Fragment, useState } from "react";
import { useApi } from "@/hooks/useApi";
import { useDebounced } from "@/hooks/useDebounced";
import { asPage, toStr, cx } from "@/lib/utils";
import { fmtDateTime } from "@/lib/format";
import type { AuditLog } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Field";
import { Badge } from "@/components/ui/Badge";
import { ErrorState, EmptyState } from "@/components/ui/States";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { TableContainer, Table, TH, TD, TR, Pagination } from "@/components/ui/Table";

function JsonBlock({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined) {
    return (
      <div className="flex-1">
        <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">{label}</p>
        <p className="rounded-lg border border-border bg-surface-3 px-3 py-2 text-xs text-muted">—</p>
      </div>
    );
  }
  let text = "";
  try {
    text = JSON.stringify(value, null, 2);
  } catch {
    text = String(value);
  }
  return (
    <div className="flex-1">
      <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">{label}</p>
      <pre className="max-h-72 overflow-auto rounded-lg border border-border bg-surface-3 p-3 font-mono text-xs leading-relaxed text-text/90">
        {text}
      </pre>
    </div>
  );
}

export function AuditLogPage() {
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<number | null>(null);

  const debouncedAction = useDebounced(action, 350);
  const debouncedEntity = useDebounced(entityType, 350);

  const params = new URLSearchParams();
  if (debouncedAction.trim()) params.set("action", debouncedAction.trim());
  if (debouncedEntity.trim()) params.set("entity_type", debouncedEntity.trim());
  params.set("page", String(page));

  const { data, loading, error, reload, errorMessage: loadError } = useApi<unknown>(
    `/api/audit-logs?${params.toString()}`,
  );

  const rows = asPage<AuditLog>(data).items;
  const paging = asPage<AuditLog>(data);
  const hasFilters = Boolean(debouncedAction.trim() || debouncedEntity.trim());

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-text">Audit log</h2>
        <p className="mt-1 text-sm text-muted">
          Immutable record of sign-ins, changes, approvals and payroll actions.
        </p>
      </div>

      <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-4 sm:flex-row sm:items-end">
        <Field label="Action contains" htmlFor="audit_action" className="flex-1">
          <Input
            id="audit_action"
            value={action}
            onChange={(e) => {
              setAction(e.target.value);
              setPage(1);
            }}
            placeholder="login, employee.update, leave.approve…"
          />
        </Field>
        <Field label="Entity type contains" htmlFor="audit_entity" className="sm:w-56">
          <Input
            id="audit_entity"
            value={entityType}
            onChange={(e) => {
              setEntityType(e.target.value);
              setPage(1);
            }}
            placeholder="employee, payroll_run…"
          />
        </Field>
        <Button variant="secondary" onClick={reload}>
          Refresh
        </Button>
        {hasFilters && (
          <Button
            variant="ghost"
            onClick={() => {
              setAction("");
              setEntityType("");
              setPage(1);
            }}
          >
            Clear
          </Button>
        )}
      </div>

      {loading && data === undefined && <TableSkeleton rows={8} cols={6} />}
      {error && !loading && <ErrorState message={loadError} onRetry={reload} />}

      {data !== undefined && rows.length === 0 && (
        <EmptyState
          title={hasFilters ? "No entries match these filters" : "No audit entries yet"}
          description={
            hasFilters
              ? "Try a broader action or entity filter."
              : "Sign-ins, employee changes, approvals and payroll actions will be recorded here."
          }
          action={
            hasFilters ? (
              <Button
                variant="secondary"
                onClick={() => {
                  setAction("");
                  setEntityType("");
                }}
              >
                Clear filters
              </Button>
            ) : undefined
          }
        />
      )}

      {rows.length > 0 && (
        <>
          <TableContainer>
            <Table>
              <thead>
                <TR>
                  <TH>Timestamp</TH>
                  <TH>Actor</TH>
                  <TH>Action</TH>
                  <TH>Entity</TH>
                  <TH align="right">Entity ID</TH>
                  <TH align="right">Changes</TH>
                </TR>
              </thead>
              <tbody>
                {rows.map((log) => (
                  <Fragment key={log.id}>
                    <TR
                      onClick={() => setExpanded((cur) => (cur === log.id ? null : log.id))}
                      className={cx(expanded === log.id && "bg-surface-2")}
                    >
                      <TD className="whitespace-nowrap tabular-nums text-muted">
                        {fmtDateTime(log.created_at)}
                      </TD>
                      <TD className="text-text/90">{toStr(log.actor_email, "—")}</TD>
                      <TD>
                        <Badge tone="accent">{toStr(log.action, "—")}</Badge>
                      </TD>
                      <TD className="text-muted">{toStr(log.entity_type, "—")}</TD>
                      <TD align="right" className="tabular-nums text-muted">
                        {log.entity_id === null || log.entity_id === undefined ? "—" : String(log.entity_id)}
                      </TD>
                      <TD align="right">
                        <span className="text-xs text-accent">
                          {expanded === log.id ? "Hide ▲" : "View ▼"}
                        </span>
                      </TD>
                    </TR>
                    {expanded === log.id && (
                      <tr key={`${log.id}-detail`} className="border-b border-border bg-surface-2">
                        <td colSpan={6} className="px-4 py-4">
                          <div className="flex flex-col gap-4 lg:flex-row">
                            <JsonBlock label="Before" value={log.before} />
                            <JsonBlock label="After" value={log.after} />
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </Table>
            <Pagination page={paging.page} pageSize={paging.page_size} total={paging.total} onPage={setPage} />
          </TableContainer>
        </>
      )}
    </div>
  );
}
