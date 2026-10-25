"use client";

import { useMemo, useState } from "react";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { asPage, isObject, toBool, toNum, toStr, WEEKDAYS } from "@/lib/utils";
import type { CompanySettings } from "@/types/api";
import { useAuth } from "@/components/auth/Auth";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select, Checkbox } from "@/components/ui/Field";
import { Modal, ConfirmDialog } from "@/components/ui/Modal";
import { ErrorState, EmptyState } from "@/components/ui/States";
import { ListSkeleton } from "@/components/ui/Skeleton";
import { TableContainer, Table, TH, TD, TR } from "@/components/ui/Table";
import { Icon } from "@/components/layout/Icon";
import { useToast } from "@/components/ui/Toast";

type Row = Record<string, unknown>;

export interface FieldDef {
  name: string;
  label: string;
  type: "text" | "number" | "date" | "time" | "checkbox";
  required?: boolean;
  placeholder?: string;
  hint?: string;
  options?: { value: string; label: string }[];
}

export interface ColumnDef {
  key: string;
  label: string;
  align?: "left" | "right";
  render?: (row: Row) => React.ReactNode;
}

function coerce(values: Record<string, string | boolean>, fields: FieldDef[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    const raw = values[f.name];
    if (f.type === "number") out[f.name] = raw === "" || raw === undefined ? null : Number(raw);
    else if (f.type === "checkbox") out[f.name] = Boolean(raw);
    else out[f.name] = raw === undefined || raw === "" ? (f.required ? "" : null) : String(raw);
  }
  return out;
}

function initialValues(fields: FieldDef[], row?: Row): Record<string, string | boolean> {
  const values: Record<string, string | boolean> = {};
  for (const f of fields) {
    const raw = row ? row[f.name] : undefined;
    if (f.type === "checkbox") values[f.name] = toBool(raw);
    else if (f.type === "number") values[f.name] = raw === undefined || raw === null ? "" : String(raw);
    else values[f.name] = raw === undefined || raw === null ? "" : String(raw);
  }
  return values;
}

/* --------------------------- generic CRUD card --------------------------- */

export function CrudSection({
  title,
  description,
  endpoint,
  fields,
  columns,
  readOnly,
  addLabel,
}: {
  title: string;
  description: string;
  endpoint: string;
  fields: FieldDef[];
  columns: ColumnDef[];
  readOnly: boolean;
  addLabel: string;
}) {
  const toast = useToast();
  const { data, loading, error, reload, errorMessage: loadError } = useApi<unknown>(endpoint);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Row | null>(null);
  const [values, setValues] = useState<Record<string, string | boolean>>(() => initialValues(fields));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Row | null>(null);
  const [deleting, setDeleting] = useState(false);

  const rows = asPage<Row>(data).items;

  const openCreate = () => {
    setEditing(null);
    setValues(initialValues(fields));
    setErrors({});
    setFormError(null);
    setModalOpen(true);
  };

  const openEdit = (row: Row) => {
    setEditing(row);
    setValues(initialValues(fields, row));
    setErrors({});
    setFormError(null);
    setModalOpen(true);
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setErrors({});
    setFormError(null);
    const body = coerce(values, fields);
    try {
      if (editing && toNum(editing.id, 0) > 0) {
        await api(`${endpoint}/${editing.id}`, { method: "PATCH", body });
        toast({ type: "success", message: `${title} updated.` });
      } else {
        await api(endpoint, { method: "POST", body });
        toast({ type: "success", message: `${title} added.` });
      }
      setModalOpen(false);
      reload();
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors);
        setFormError(err.status === 422 ? null : err.message);
      } else {
        setFormError(errorMessage(err));
      }
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api(`${endpoint}/${deleteTarget.id}`, { method: "DELETE" });
      toast({ type: "success", message: "Deleted." });
      setDeleteTarget(null);
      reload();
    } catch (err) {
      toast({ type: "error", message: errorMessage(err) });
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Card
      title={title}
      description={description}
      actions={
        readOnly ? (
          <span className="text-xs font-medium text-muted">Admin only</span>
        ) : (
          <Button size="sm" onClick={openCreate}>
            <Icon name="plus" className="h-4 w-4" /> {addLabel}
          </Button>
        )
      }
    >
      {loading && data === undefined && <ListSkeleton rows={3} />}
      {error && !loading && <ErrorState message={loadError} onRetry={reload} />}
      {data !== undefined && rows.length === 0 && (
        <EmptyState
          compact
          title={`No ${title.toLowerCase()} yet`}
          description={readOnly ? "An administrator can add these." : "Add the first entry."}
          action={readOnly ? undefined : <Button size="sm" onClick={openCreate}>{addLabel}</Button>}
        />
      )}
      {rows.length > 0 && (
        <TableContainer className="max-h-[50vh]">
          <Table>
            <thead>
              <TR>
                {columns.map((c) => (
                  <TH key={c.key} align={c.align}>
                    {c.label}
                  </TH>
                ))}
                {!readOnly && <TH align="right">Actions</TH>}
              </TR>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <TR key={toStr(row.id, `row-${i}`)}>
                  {columns.map((c) => (
                    <TD key={c.key} align={c.align} className={c.align === "right" ? "tabular-nums" : undefined}>
                      {c.render ? c.render(row) : toStr(row[c.key], "—")}
                    </TD>
                  ))}
                  {!readOnly && (
                    <TD align="right">
                      <span className="flex justify-end gap-2">
                        <Button size="sm" variant="secondary" onClick={() => openEdit(row)}>
                          Edit
                        </Button>
                        <Button size="sm" variant="danger" onClick={() => setDeleteTarget(row)}>
                          <Icon name="trash" className="h-3.5 w-3.5" />
                        </Button>
                      </span>
                    </TD>
                  )}
                </TR>
              ))}
            </tbody>
          </Table>
        </TableContainer>
      )}

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={`${editing ? "Edit" : "Add"} — ${title}`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setModalOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" form={`crud-${endpoint.replace(/\W+/g, "-")}`} loading={saving}>
              Save
            </Button>
          </>
        }
      >
        <form
          id={`crud-${endpoint.replace(/\W+/g, "-")}`}
          onSubmit={save}
          className="space-y-4"
          noValidate
        >
          {formError && (
            <div role="alert" className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
              {formError}
            </div>
          )}
          {fields.map((f) => (
            <Field key={f.name} label={f.label} htmlFor={`field-${f.name}`} error={errors[f.name]} hint={f.hint} required={f.required}>
              {f.type === "checkbox" ? (
                <Checkbox
                  label={f.placeholder ?? f.label}
                  checked={toBool(values[f.name])}
                  onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.checked }))}
                />
              ) : f.options ? (
                <Select
                  id={`field-${f.name}`}
                  value={String(values[f.name] ?? "")}
                  onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                >
                  <option value="">Select…</option>
                  {f.options.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </Select>
              ) : (
                <Input
                  id={`field-${f.name}`}
                  type={f.type === "number" ? "number" : f.type === "date" ? "date" : f.type === "time" ? "time" : "text"}
                  value={String(values[f.name] ?? "")}
                  placeholder={f.placeholder}
                  onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                  required={f.required}
                />
              )}
            </Field>
          ))}
        </form>
      </Modal>

      <ConfirmDialog
        open={deleteTarget !== null}
        title={`Delete ${title.toLowerCase()}`}
        message={
          deleteTarget
            ? `Delete “${toStr(columns[0] ? deleteTarget[columns[0].key] : deleteTarget.name, "this entry")}”? This cannot be undone.`
            : ""
        }
        confirmLabel="Delete"
        danger
        loading={deleting}
        onConfirm={remove}
        onCancel={() => setDeleteTarget(null)}
      />
    </Card>
  );
}

/* ---------------------------- company settings --------------------------- */

function CompanySettingsForm({ readOnly }: { readOnly: boolean }) {
  const { data, loading, error, reload, errorMessage: loadError } = useApi<unknown>("/api/org/settings");

  const settings: CompanySettings = useMemo(() => {
    if (!isObject(data)) return {};
    const inner = isObject(data.settings) ? (data.settings as Row) : data;
    return {
      office_start_time: toStr(inner.office_start_time, "09:00").slice(0, 5),
      grace_period_minutes: toNum(inner.grace_period_minutes, 15),
      weekend_days: Array.isArray(inner.weekend_days)
        ? (inner.weekend_days as string[])
        : ["Saturday", "Sunday"],
      office_lat: inner.office_lat === undefined ? null : Number(inner.office_lat),
      office_lng: inner.office_lng === undefined ? null : Number(inner.office_lng),
      geofence_radius_m: toNum(inner.geofence_radius_m, 1000),
      timezone: toStr(inner.timezone, "Asia/Karachi"),
      half_day_threshold_hours: toNum(inner.half_day_threshold_hours, 5),
    };
  }, [data]);

  if (loading && data === undefined) return <ListSkeleton rows={4} />;
  if (error && !loading) return <ErrorState message={loadError} onRetry={reload} />;

  // Keyed by the server values so the editor re-seeds itself after a save
  // returns normalised values, instead of resetting form state in an effect.
  return (
    <SettingsEditor
      key={JSON.stringify(settings)}
      settings={settings}
      readOnly={readOnly}
      onSaved={reload}
    />
  );
}

function SettingsEditor({
  settings,
  readOnly,
  onSaved,
}: {
  settings: CompanySettings;
  readOnly: boolean;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [values, setValues] = useState<Record<string, string | string[]>>(() => ({
    office_start_time: settings.office_start_time ?? "09:00",
    grace_period_minutes: String(settings.grace_period_minutes ?? 15),
    weekend_days: settings.weekend_days ?? ["Saturday", "Sunday"],
    office_lat:
      settings.office_lat === null || settings.office_lat === undefined
        ? ""
        : String(settings.office_lat),
    office_lng:
      settings.office_lng === null || settings.office_lng === undefined
        ? ""
        : String(settings.office_lng),
    geofence_radius_m: String(settings.geofence_radius_m ?? 1000),
    timezone: settings.timezone ?? "Asia/Karachi",
    half_day_threshold_hours: String(settings.half_day_threshold_hours ?? 5),
  }));
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const toggleWeekend = (day: string) =>
    setValues((v) => {
      const current = Array.isArray(v.weekend_days) ? v.weekend_days : [];
      const next = current.includes(day) ? current.filter((d) => d !== day) : [...current, day];
      return { ...v, weekend_days: next };
    });

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setErrors({});
    setFormError(null);
    try {
      await api("/api/org/settings", {
        method: "PATCH",
        body: {
          office_start_time: values.office_start_time,
          grace_period_minutes: Number(values.grace_period_minutes),
          weekend_days: values.weekend_days ?? [],
          office_lat: values.office_lat === "" ? null : Number(values.office_lat),
          office_lng: values.office_lng === "" ? null : Number(values.office_lng),
          geofence_radius_m: Number(values.geofence_radius_m),
          timezone: values.timezone,
          half_day_threshold_hours: Number(values.half_day_threshold_hours),
        },
      });
      toast({ type: "success", message: "Company settings saved." });
      onSaved();
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

  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setValues((v) => ({ ...v, [key]: e.target.value }));

  return (
    <Card
      title="Office settings"
      description="Drives late detection, geofencing, weekends and half-day rules."
      actions={readOnly ? <span className="text-xs font-medium text-muted">Admin only</span> : undefined}
    >
      <form onSubmit={save} className="space-y-4" noValidate>
        {formError && (
          <div role="alert" className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
            {formError}
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Office start time" htmlFor="office_start_time" error={errors.office_start_time} required>
            <Input
              id="office_start_time"
              type="time"
              value={values.office_start_time ?? "09:00"}
              onChange={set("office_start_time")}
              disabled={readOnly}
              required
            />
          </Field>
          <Field label="Grace period (minutes)" htmlFor="grace_period_minutes" error={errors.grace_period_minutes} required>
            <Input
              id="grace_period_minutes"
              type="number"
              min="0"
              value={values.grace_period_minutes ?? "15"}
              onChange={set("grace_period_minutes")}
              disabled={readOnly}
              required
            />
          </Field>
          <Field label="Timezone" htmlFor="timezone" error={errors.timezone} required>
            <Input
              id="timezone"
              value={values.timezone ?? "Asia/Karachi"}
              onChange={set("timezone")}
              disabled={readOnly}
              required
            />
          </Field>
        </div>

        <fieldset className="rounded-lg border border-border bg-surface-2 p-4" disabled={readOnly}>
          <legend className="px-1 text-xs font-medium text-muted">Weekend days</legend>
          <div className="flex flex-wrap gap-x-5 gap-y-2">
            {WEEKDAYS.map((day) => (
              <Checkbox
                key={day}
                label={day}
                checked={(values.weekend_days ?? []).includes(day)}
                onChange={() => toggleWeekend(day)}
                disabled={readOnly}
              />
            ))}
          </div>
        </fieldset>

        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Office latitude" htmlFor="office_lat" error={errors.office_lat} hint="e.g. 24.8607">
            <Input
              id="office_lat"
              type="number"
              step="any"
              value={values.office_lat ?? ""}
              onChange={set("office_lat")}
              disabled={readOnly}
            />
          </Field>
          <Field label="Office longitude" htmlFor="office_lng" error={errors.office_lng} hint="e.g. 67.0011">
            <Input
              id="office_lng"
              type="number"
              step="any"
              value={values.office_lng ?? ""}
              onChange={set("office_lng")}
              disabled={readOnly}
            />
          </Field>
          <Field label="Geofence radius (m)" htmlFor="geofence_radius_m" error={errors.geofence_radius_m} required>
            <Input
              id="geofence_radius_m"
              type="number"
              min="0"
              value={values.geofence_radius_m ?? "1000"}
              onChange={set("geofence_radius_m")}
              disabled={readOnly}
              required
            />
          </Field>
        </div>

        <Field
          label="Half-day threshold (hours)"
          htmlFor="half_day_threshold_hours"
          error={errors.half_day_threshold_hours}
          hint="Worked hours below this value count as a half day."
          required
        >
          <Input
            id="half_day_threshold_hours"
            type="number"
            step="0.5"
            min="0"
            value={values.half_day_threshold_hours ?? "5"}
            onChange={set("half_day_threshold_hours")}
            disabled={readOnly}
            required
          />
        </Field>

        {!readOnly && (
          <div className="flex justify-end">
            <Button type="submit" loading={saving}>
              Save settings
            </Button>
          </div>
        )}
      </form>
    </Card>
  );
}

/* --------------------------------- page ---------------------------------- */

export function SettingsPage() {
  const { user } = useAuth();
  const readOnly = user?.role !== "admin";

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-text">Settings</h2>
        <p className="mt-1 text-sm text-muted">
          {readOnly
            ? "Read-only view — an administrator account is required to change these values."
            : "Company rules, organisation structure, leave types and holidays."}
        </p>
      </div>

      {readOnly && (
        <div className="rounded-lg border border-info/40 bg-info/10 px-4 py-3 text-sm text-info">
          Admin only — you are viewing the current configuration without the ability to edit it.
        </div>
      )}

      <CompanySettingsForm readOnly={readOnly} />

      <div className="grid gap-4 xl:grid-cols-2">
        <CrudSection
          title="Departments"
          description="Used across employees, attendance and payroll reporting."
          endpoint="/api/org/departments"
          readOnly={readOnly}
          addLabel="Add department"
          fields={[{ name: "name", label: "Department name", type: "text", required: true, placeholder: "Engineering" }]}
          columns={[{ key: "name", label: "Name" }]}
        />

        <CrudSection
          title="Designations"
          description="Job titles employees can be assigned to."
          endpoint="/api/org/designations"
          readOnly={readOnly}
          addLabel="Add designation"
          fields={[{ name: "name", label: "Designation name", type: "text", required: true, placeholder: "Software Engineer" }]}
          columns={[{ key: "name", label: "Name" }]}
        />

        <CrudSection
          title="Leave types"
          description="Quota and paid/unpaid rules for each leave code."
          endpoint="/api/org/leave-types"
          readOnly={readOnly}
          addLabel="Add leave type"
          fields={[
            { name: "name", label: "Name", type: "text", required: true, placeholder: "Annual leave" },
            { name: "code", label: "Code", type: "text", required: true, placeholder: "ANNUAL" },
            { name: "yearly_quota", label: "Yearly quota (days)", type: "number", required: true, placeholder: "14", hint: "Leave empty for unlimited." },
            { name: "is_paid", label: "Paid leave", type: "checkbox", placeholder: "This leave type is paid" },
          ]}
          columns={[
            { key: "name", label: "Name" },
            { key: "code", label: "Code" },
            { key: "yearly_quota", label: "Quota", align: "right", render: (r) => (r.yearly_quota === null || r.yearly_quota === undefined ? "Unlimited" : String(r.yearly_quota)) },
            { key: "is_paid", label: "Paid", render: (r) => (toBool(r.is_paid) ? "Yes" : "No") },
          ]}
        />

        <CrudSection
          title="Holidays"
          description="Public holidays excluded from leave working days."
          endpoint="/api/org/holidays"
          readOnly={readOnly}
          addLabel="Add holiday"
          fields={[
            { name: "name", label: "Holiday name", type: "text", required: true, placeholder: "Independence Day" },
            { name: "date", label: "Date", type: "date", required: true },
          ]}
          columns={[
            { key: "name", label: "Name" },
            { key: "date", label: "Date" },
          ]}
        />
      </div>
    </div>
  );
}
