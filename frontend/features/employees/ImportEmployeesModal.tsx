"use client";

import { useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { isObject, toNum } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/ui/States";
import { Badge } from "@/components/ui/Badge";
import { Table, TH, TD, TR } from "@/components/ui/Table";

interface Issue {
  row: string;
  field: string;
  reason: string;
}

interface ImportReport {
  total: number | null;
  valid: number | null;
  created: number | null;
  issues: Issue[];
}

const ERROR_KEYS = ["errors", "issues", "problems", "invalid_rows"];
const LIST_KEYS = ["rows", "results", "items", "report", "details"];

function rowIssue(r: Record<string, unknown>): Issue | null {
  const reason = r.reason ?? r.error ?? r.message ?? r.detail ?? r.msg;
  if (reason === undefined || reason === null || reason === "") return null;
  return {
    row: String(r.row ?? r.row_number ?? r.line ?? r.index ?? "—"),
    field: String(r.field ?? r.column ?? r.key ?? "—"),
    reason: String(reason),
  };
}

function normaliseReport(payload: unknown): ImportReport {
  const source: Record<string, unknown> = isObject(payload) ? payload : {};

  let issues: Issue[] = [];
  for (const key of ERROR_KEYS) {
    const list = source[key];
    if (Array.isArray(list)) {
      issues = list
        .filter(isObject)
        .map((r) => rowIssue(r) ?? { row: String(r.row ?? "—"), field: "—", reason: "Invalid row" });
      break;
    }
  }

  if (!issues.length) {
    for (const key of LIST_KEYS) {
      const list = source[key];
      if (Array.isArray(list)) {
        issues = list.filter(isObject).map(rowIssue).filter(Boolean) as Issue[];
        break;
      }
    }
  }
  if (!issues.length && Array.isArray(payload)) {
    issues = payload.filter(isObject).map(rowIssue).filter(Boolean) as Issue[];
  }

  const total = toNum(source.total ?? source.total_rows ?? source.read, Number.NaN);
  const valid = toNum(
    source.valid ?? source.valid_rows ?? source.success,
    Number.isNaN(total) ? Number.NaN : Math.max(total - issues.length, 0),
  );
  const created = toNum(source.created ?? source.inserted ?? source.imported, Number.NaN);

  return {
    total: Number.isNaN(total) ? null : total,
    valid: Number.isNaN(valid) ? null : valid,
    created: Number.isNaN(created) ? null : created,
    issues,
  };
}

export function ImportEmployeesModal({
  open,
  onClose,
  onImported,
}: {
  open: boolean;
  onClose: () => void;
  onImported: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<"idle" | "checking" | "importing" | "done">("idle");
  const [report, setReport] = useState<ImportReport | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setFile(null);
    setReport(null);
    setError(null);
    setResult(null);
    setPhase("idle");
    if (inputRef.current) inputRef.current.value = "";
  };

  const close = () => {
    onClose();
    setTimeout(reset, 200);
  };

  const runDryRun = async (selected: File) => {
    setPhase("checking");
    setError(null);
    setReport(null);
    const fd = new FormData();
    fd.append("file", selected);
    try {
      const payload = await api<unknown>(`/api/employees/import?dry_run=true`, {
        method: "POST",
        formData: fd,
      });
      setReport(normaliseReport(payload));
      setPhase("idle");
    } catch (err) {
      setError(errorMessage(err));
      setPhase("idle");
    }
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0] ?? null;
    setFile(selected);
    if (selected) void runDryRun(selected);
  };

  const confirmImport = async () => {
    if (!file) return;
    setPhase("importing");
    setError(null);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const payload = await api<unknown>(`/api/employees/import?dry_run=false`, {
        method: "POST",
        formData: fd,
      });
      const done = normaliseReport(payload);
      setResult(
        done.created !== null
          ? `${done.created} employee(s) imported${done.issues.length ? `, ${done.issues.length} row(s) had issues` : ""}.`
          : "Import completed.",
      );
      setReport(done);
      setPhase("done");
      onImported();
    } catch (err) {
      setError(errorMessage(err));
      setPhase("idle");
    }
  };

  const issueCount = report?.issues.length ?? 0;

  return (
    <Modal
      open={open}
      onClose={close}
      title="Import employees from CSV"
      description="Dry-run first: the preview shows every row/field problem before anything is written."
      size="xl"
      footer={
        phase === "done" ? (
          <Button onClick={close}>Close</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={close} disabled={phase === "checking" || phase === "importing"}>
              Cancel
            </Button>
            <Button
              onClick={confirmImport}
              disabled={!file || !report || issueCount > 0 || phase !== "idle"}
              loading={phase === "importing"}
            >
              Confirm import
            </Button>
          </>
        )
      }
    >
      <div className="space-y-4">
        {error && (
          <div role="alert" className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
            {error}
          </div>
        )}
        {result && (
          <div className="rounded-lg border border-success/40 bg-success/10 px-4 py-3 text-sm text-success">
            {result}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={inputRef}
            type="file"
            accept=".csv,text/csv"
            onChange={onFileChange}
            aria-label="CSV file"
            className="block w-full cursor-pointer rounded-lg border border-dashed border-border bg-surface-2 px-3 py-3 text-sm text-muted file:mr-3 file:rounded-md file:border-0 file:bg-accent file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-accent-ink hover:border-accent/60 focus:outline-none focus:ring-2 focus:ring-accent/40"
          />
        </div>

        {phase === "checking" && (
          <p className="text-sm text-muted">Running dry-run — validating rows…</p>
        )}

        {report && (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-border bg-surface-2 p-3">
                <p className="text-xs text-muted">Rows read</p>
                <p className="text-xl font-semibold tabular-nums text-text">
                  {report.total ?? "—"}
                </p>
              </div>
              <div className="rounded-lg border border-border bg-surface-2 p-3">
                <p className="text-xs text-muted">Valid rows</p>
                <p className="text-xl font-semibold tabular-nums text-success">
                  {report.valid ?? "—"}
                </p>
              </div>
              <div className="rounded-lg border border-border bg-surface-2 p-3">
                <p className="text-xs text-muted">Issues</p>
                <p
                  className={`text-xl font-semibold tabular-nums ${
                    issueCount > 0 ? "text-danger" : "text-text"
                  }`}
                >
                  {issueCount}
                </p>
              </div>
            </div>

            {issueCount === 0 ? (
              <EmptyState
                compact
                title="Dry-run passed — no row errors found"
                description="Confirm to write these rows to the employee directory."
              />
            ) : (
              <div className="overflow-hidden rounded-lg border border-border">
                <div className="max-h-72 overflow-auto">
                  <Table>
                    <thead>
                      <TR>
                        <TH>Row</TH>
                        <TH>Field</TH>
                        <TH>Reason</TH>
                      </TR>
                    </thead>
                    <tbody>
                      {report.issues.map((issue, i) => (
                        <TR key={`${issue.row}-${issue.field}-${i}`}>
                          <TD className="tabular-nums text-muted">{issue.row}</TD>
                          <TD>
                            <code className="rounded bg-surface-3 px-1.5 py-0.5 text-xs text-text">
                              {issue.field}
                            </code>
                          </TD>
                          <TD className="text-danger">{issue.reason}</TD>
                        </TR>
                      ))}
                    </tbody>
                  </Table>
                </div>
              </div>
            )}

            <div className="flex items-center gap-2 text-xs text-muted">
              <Badge tone={issueCount > 0 ? "warn" : "ok"}>
                {issueCount > 0 ? "Fix issues to confirm" : "Ready to import"}
              </Badge>
              {issueCount > 0 && "Nothing has been written yet — the import is blocked until every row passes."}
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
