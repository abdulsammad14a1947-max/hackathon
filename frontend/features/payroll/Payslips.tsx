"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { downloadFile, errorMessage } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { asPage, toNum } from "@/lib/utils";
import { fmtMoney, monthName } from "@/lib/format";
import type { Payslip } from "@/types/api";
import { Card, StatCard } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ErrorState, EmptyState } from "@/components/ui/States";
import { TableSkeleton, ListSkeleton, StatsSkeleton } from "@/components/ui/Skeleton";
import { TableContainer, Table, TH, TD, TR } from "@/components/ui/Table";
import { Icon } from "@/components/layout/Icon";
import { useToast } from "@/components/ui/Toast";

function periodLabel(p: Payslip): string {
  return `${monthName(toNum(p.period_month, 1))} ${p.period_year}`;
}

function payslipKey(p: Payslip): number {
  return toNum(p.item_id ?? p.id, 0);
}

export function PayslipList() {
  const router = useRouter();
  const toast = useToast();
  const { data, loading, error, reload, errorMessage: loadError } = useApi<unknown>("/api/payroll/payslips/me");
  const [downloading, setDownloading] = useState<number | null>(null);

  const rows = asPage<Payslip>(data).items;

  const download = async (p: Payslip) => {
    const key = payslipKey(p);
    setDownloading(key);
    try {
      await downloadFile(`/api/payroll/payslips/${key}/pdf`, `payslip-${p.period_year}-${String(p.period_month).padStart(2, "0")}.pdf`);
      toast({ type: "success", message: `Payslip for ${periodLabel(p)} downloaded.` });
    } catch (err) {
      toast({ type: "error", message: errorMessage(err) });
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-text">My payslips</h2>
        <p className="mt-1 text-sm text-muted">
          Download PDFs for every finalized payroll run.
        </p>
      </div>

      {loading && data === undefined && <TableSkeleton rows={5} cols={5} />}
      {error && !loading && <ErrorState message={loadError} onRetry={reload} />}
      {data !== undefined && rows.length === 0 && (
        <EmptyState
          title="No payslips yet"
          description="Payslips appear here as soon as payroll is finalized for your first month."
        />
      )}
      {rows.length > 0 && (
        <TableContainer>
          <Table>
            <thead>
              <TR>
                <TH>Period</TH>
                <TH align="right">Gross</TH>
                <TH align="right">Deductions</TH>
                <TH align="right">Tax</TH>
                <TH align="right">Net pay</TH>
                <TH align="right">Actions</TH>
              </TR>
            </thead>
            <tbody>
              {rows.map((p) => (
                <TR key={payslipKey(p)}>
                  <TD className="font-medium text-text">{periodLabel(p)}</TD>
                  <TD align="right">{fmtMoney(p.gross)}</TD>
                  <TD align="right">{fmtMoney(p.deduction_amount)}</TD>
                  <TD align="right">{fmtMoney(p.tax)}</TD>
                  <TD align="right" className="font-semibold">{fmtMoney(p.net_pay)}</TD>
                  <TD align="right">
                    <span className="flex justify-end gap-2">
                      <Button size="sm" variant="secondary" onClick={() => router.push(`/payslips/${payslipKey(p)}`)}>
                        View
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => download(p)}
                        loading={downloading === payslipKey(p)}
                      >
                        <Icon name="download" className="h-4 w-4" /> PDF
                      </Button>
                    </span>
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        </TableContainer>
      )}
    </div>
  );
}

export function PayslipViewer({ itemId }: { itemId: number }) {
  const router = useRouter();
  const { data, loading, error, reload, errorMessage: loadError } = useApi<unknown>("/api/payroll/payslips/me");
  const [status, setStatus] = useState<"idle" | "downloading" | "done" | "error">("idle");
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const started = useRef(false);

  const rows = asPage<Payslip>(data).items;
  const payslip = rows.find((p) => payslipKey(p) === itemId) ?? null;

  const fetchPdf = async () => {
    setStatus("downloading");
    setDownloadError(null);
    try {
      await downloadFile(
        `/api/payroll/payslips/${itemId}/pdf`,
        `payslip-${payslip?.period_year ?? "run"}-${payslip ? String(payslip.period_month).padStart(2, "0") : ""}.pdf`,
      );
      setStatus("done");
    } catch (err) {
      setDownloadError(errorMessage(err));
      setStatus("error");
    }
  };

  useEffect(() => {
    if (started.current || loading) return;
    started.current = true;
    void fetchPdf();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading]);

  if (error) {
    return <ErrorState message={loadError} onRetry={reload} />;
  }
  if (loading || !payslip) {
    return loading ? (
      <div className="space-y-4">
        <StatsSkeleton count={3} />
        <ListSkeleton rows={3} />
      </div>
    ) : (
      <EmptyState
        title="Payslip not found"
        description="This payslip is not part of your finalized payroll history."
        action={<Button onClick={() => router.push("/payslips")}>Back to payslips</Button>}
      />
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <button
        onClick={() => router.push("/payslips")}
        className="text-xs font-medium text-accent hover:text-accent-hover"
      >
        ← Back to payslips
      </button>

      <Card
        title={`Payslip — ${periodLabel(payslip)}`}
        description="PDF download starts automatically."
        actions={
          <Button onClick={fetchPdf} loading={status === "downloading"} variant="secondary">
            <Icon name="download" className="h-4 w-4" />
            {status === "done" ? "Download again" : "Download PDF"}
          </Button>
        }
      >
        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard label="Gross pay" value={fmtMoney(payslip.gross)} />
          <StatCard label="Deductions" value={fmtMoney(payslip.deduction_amount)} tone="warn" />
          <StatCard label="Net pay" value={fmtMoney(payslip.net_pay)} tone="ok" />
        </div>

        <div className="mt-4 space-y-2 rounded-lg border border-border bg-surface-2 px-4 py-3 text-sm">
          <div className="flex justify-between">
            <span className="text-muted">Tax</span>
            <span className="tabular-nums">{fmtMoney(payslip.tax)}</span>
          </div>
          {payslip.employee_code && (
            <div className="flex justify-between">
              <span className="text-muted">Employee code</span>
              <span className="font-mono">{payslip.employee_code}</span>
            </div>
          )}
          <div className="flex justify-between">
            <span className="text-muted">Period</span>
            <span>
              {monthName(toNum(payslip.period_month, 1))} {payslip.period_year}
            </span>
          </div>
        </div>

        <div className="mt-4" aria-live="polite">
          {status === "downloading" && (
            <p className="flex items-center gap-2 text-sm text-muted">
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
              Preparing your PDF…
            </p>
          )}
          {status === "done" && (
            <p className="text-sm text-success">PDF downloaded to your device.</p>
          )}
          {status === "error" && (
            <div className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
              {downloadError}
              <Button size="sm" variant="secondary" className="ml-3" onClick={fetchPdf}>
                Retry
              </Button>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
