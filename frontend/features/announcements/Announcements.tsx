"use client";

import { useEffect, useMemo, useState } from "react";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { asPage, cx } from "@/lib/utils";
import { fmtDateTime } from "@/lib/format";
import type { Announcement } from "@/types/api";
import { useAuth } from "@/components/auth/Auth";
import { Button } from "@/components/ui/Button";
import { Modal, ConfirmDialog } from "@/components/ui/Modal";
import { Field, Input, Textarea } from "@/components/ui/Field";
import { Badge } from "@/components/ui/Badge";
import { ErrorState, EmptyState } from "@/components/ui/States";
import { ListSkeleton } from "@/components/ui/Skeleton";
import { Icon } from "@/components/layout/Icon";
import { useToast } from "@/components/ui/Toast";

const READ_KEY = "hcm_read_announcements";

function readLocal(): number[] {
  try {
    const raw = window.localStorage.getItem(READ_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(parsed) ? (parsed as number[]) : [];
  } catch {
    return [];
  }
}

function writeLocal(ids: number[]) {
  try {
    window.localStorage.setItem(READ_KEY, JSON.stringify(ids.slice(-200)));
  } catch {
    /* ignore */
  }
}

function CreateAnnouncementModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const toast = useToast();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setErrors({});
    setFormError(null);
    try {
      await api("/api/announcements", {
        method: "POST",
        body: { title: title.trim(), body: body.trim() },
      });
      toast({ type: "success", message: "Announcement published." });
      setTitle("");
      setBody("");
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
      title="New announcement"
      description="Visible to everyone in your company."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" form="announcement-form" loading={saving}>
            Publish
          </Button>
        </>
      }
    >
      <form id="announcement-form" onSubmit={submit} className="space-y-4" noValidate>
        {formError && (
          <div role="alert" className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
            {formError}
          </div>
        )}
        <Field label="Title" htmlFor="ann_title" error={errors.title} required>
          <Input id="ann_title" value={title} onChange={(e) => setTitle(e.target.value)} required />
        </Field>
        <Field label="Message" htmlFor="ann_body" error={errors.body} required>
          <Textarea
            id="ann_body"
            rows={5}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Office will be closed on Friday for the annual maintenance shutdown."
            required
          />
        </Field>
      </form>
    </Modal>
  );
}

export function AnnouncementsList() {
  const { user } = useAuth();
  const toast = useToast();
  const { data, loading, error, reload, errorMessage: loadError } = useApi<unknown>("/api/announcements");
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Announcement | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [readIds, setReadIds] = useState<number[]>([]);

  /* eslint-disable react-hooks/set-state-in-effect -- one-time read of the locally
     tracked read-state after mount: localStorage is unavailable during SSR/prerender,
     so a lazy useState initialiser would cause a hydration mismatch. */
  useEffect(() => setReadIds(readLocal()), []);
  /* eslint-enable react-hooks/set-state-in-effect */

  const rows = useMemo(() => asPage<Announcement>(data).items, [data]);
  const canPost = user?.role === "admin" || user?.role === "hr";

  const isRead = (a: Announcement) =>
    a.is_read !== undefined && a.is_read !== null ? Boolean(a.is_read) : readIds.includes(a.id);

  const markRead = (a: Announcement) => {
    if (isRead(a)) return;
    const next = [...readIds, a.id];
    setReadIds(next);
    writeLocal(next);
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api(`/api/announcements/${deleteTarget.id}`, { method: "DELETE" });
      toast({ type: "success", message: "Announcement deleted." });
      setDeleteTarget(null);
      reload();
    } catch (err) {
      toast({ type: "error", message: errorMessage(err) });
    } finally {
      setDeleting(false);
    }
  };

  const canDelete = (a: Announcement) =>
    user?.role === "admin" || (a.created_by !== undefined && a.created_by === user?.id);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-text">Announcements</h2>
          <p className="mt-1 text-sm text-muted">Company-wide updates from HR and management.</p>
        </div>
        {canPost && (
          <Button onClick={() => setCreateOpen(true)}>
            <Icon name="plus" className="h-4 w-4" /> New announcement
          </Button>
        )}
      </div>

      {loading && data === undefined && <ListSkeleton rows={4} />}
      {error && !loading && <ErrorState message={loadError} onRetry={reload} />}
      {data !== undefined && rows.length === 0 && (
        <EmptyState
          title="No announcements yet"
          description={
            canPost
              ? "Publish the first update — everyone in the company will see it."
              : "Announcements from your HR team will appear here."
          }
          action={canPost ? <Button onClick={() => setCreateOpen(true)}>New announcement</Button> : undefined}
        />
      )}

      <div className="space-y-4">
        {rows.map((a) => {
          const read = isRead(a);
          return (
            <article
              key={a.id}
              className={cx(
                "rounded-xl border bg-surface p-5 shadow-[var(--shadow-card)] transition-[border-color,transform] duration-300 ease-snappy hover:-translate-y-0.5 hover:border-border-strong",
                read ? "border-border" : "border-accent/40 bg-accent/5",
              )}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-base font-semibold text-text">{a.title}</h3>
                    {!read && <Badge tone="accent">Unread</Badge>}
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-muted">
                    {a.body}
                  </p>
                  <p className="mt-3 text-xs text-muted/70">
                    {fmtDateTime(a.created_at)}
                    {a.created_by_name ? ` · ${a.created_by_name}` : ""}
                    {a.audience ? ` · audience: ${a.audience}` : ""}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  {!read && (
                    <Button size="sm" variant="secondary" onClick={() => markRead(a)}>
                      Mark as read
                    </Button>
                  )}
                  {canDelete(a) && (
                    <Button size="sm" variant="danger" onClick={() => setDeleteTarget(a)}>
                      <Icon name="trash" className="h-4 w-4" /> Delete
                    </Button>
                  )}
                </div>
              </div>
            </article>
          );
        })}
      </div>

      <CreateAnnouncementModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => reload()}
      />
      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete announcement"
        message={
          deleteTarget
            ? `Delete “${deleteTarget.title}”? This cannot be undone.`
            : ""
        }
        confirmLabel="Delete"
        danger
        loading={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
