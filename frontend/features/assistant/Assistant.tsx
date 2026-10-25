"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError, errorMessage } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { toNum } from "@/lib/utils";
import type { ChatResponse, ChatToolCall, SmartLeave } from "@/types/api";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Field, Input, Textarea } from "@/components/ui/Field";
import { Icon } from "@/components/layout/Icon";
import { useToast } from "@/components/ui/Toast";

type Kind = "ai" | "error" | "fallback" | "system";

interface Message {
  id: number;
  role: "user" | "assistant";
  text: string;
  kind?: Kind;
  provider?: string;
  tools?: ChatToolCall[];
  smartLeave?: SmartLeave;
  submitted?: boolean;
}

const SUGGESTIONS = [
  "How many days of annual leave do I have left?",
  "I want to take 3 days off next month",
  "What is my attendance status today?",
  "When was the last payroll run?",
];

let nextId = 1;

/* ------------------------------ leave card ------------------------------- */

function SmartLeaveCard({
  initial,
  onSubmitted,
  onDiscard,
}: {
  initial: SmartLeave;
  onSubmitted: (workingDays: number) => void;
  onDiscard: () => void;
}) {
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [form, setForm] = useState({
    type: initial.type ?? "",
    start: initial.start ?? "",
    end: initial.end ?? "",
    reason: initial.reason ?? "",
  });

  const set = (key: keyof typeof form) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
      setForm((f) => ({ ...f, [key]: e.target.value }));

  const submit = async () => {
    setSaving(true);
    setError(null);
    try {
      const created = await api<{ working_days?: number | string }>("/api/leave/requests", {
        method: "POST",
        body: {
          leave_type_code: form.type,
          start_date: form.start,
          end_date: form.end,
          reason: form.reason,
        },
      });
      onSubmitted(toNum(created?.working_days, toNum(initial.working_days)));
      setDone(true);
      setEditing(false);
    } catch (err) {
      const msg =
        err instanceof ApiError && err.status === 422
          ? errorMessage(err)
          : errorMessage(err);
      setError(msg);
      toast({ type: "error", message: msg });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mt-3 rounded-lg border border-accent/40 bg-accent/5 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-accent">
          Draft leave request
        </p>
        <div className="flex gap-1.5">
          <Badge tone="accent">Needs your confirmation</Badge>
        </div>
      </div>

      {done ? (
        <div className="mt-3 rounded-lg border border-success/40 bg-success/10 px-3 py-2 text-sm text-success">
          Submitted — the request is now waiting for HR approval.
        </div>
      ) : editing ? (
        <div className="mt-3 space-y-3">
          <Field label="Leave type code" htmlFor="sl_type">
            <Input id="sl_type" value={form.type} onChange={set("type")} placeholder="ANNUAL" />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Start date" htmlFor="sl_start">
              <Input id="sl_start" type="date" value={form.start} onChange={set("start")} />
            </Field>
            <Field label="End date" htmlFor="sl_end">
              <Input id="sl_end" type="date" value={form.end} onChange={set("end")} />
            </Field>
          </div>
          <Field label="Reason" htmlFor="sl_reason">
            <Textarea id="sl_reason" rows={2} value={form.reason} onChange={set("reason")} />
          </Field>
        </div>
      ) : (
        <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
          <div className="flex justify-between gap-3 sm:col-span-2">
            <dt className="text-muted">Type</dt>
            <dd className="font-medium text-text">{form.type || "—"}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-muted">Start</dt>
            <dd className="tabular-nums text-text">{fmtDate(form.start)}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-muted">End</dt>
            <dd className="tabular-nums text-text">{fmtDate(form.end)}</dd>
          </div>
          <div className="flex justify-between gap-3 sm:col-span-2">
            <dt className="text-muted">Working days</dt>
            <dd className="font-medium text-text">
              {toNum(initial.working_days) || "—"}
            </dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-muted">Reason</dt>
            <dd className="mt-1 text-text/90">{form.reason || "—"}</dd>
          </div>
        </dl>
      )}

      {error && (
        <p role="alert" className="mt-3 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      {!done && (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button size="sm" onClick={() => (editing ? submit() : setEditing(true))} loading={saving}>
            {editing ? "Submit request" : "Confirm & submit"}
          </Button>
          {!editing && (
            <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
              Edit
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={onDiscard}>
            Discard
          </Button>
        </div>
      )}
      <p className="mt-2 text-[11px] text-muted">
        The assistant never submits on your behalf — nothing is sent until you confirm.
      </p>
    </div>
  );
}

/* --------------------------------- chat ---------------------------------- */

export function AssistantChat() {
  const toast = useToast();
  const [messages, setMessages] = useState<Message[]>([
    {
      id: nextId++,
      role: "assistant",
      kind: "ai",
      provider: "unknown",
      text:
        "Hi! I'm the HCM Lite assistant. I can explain leave balances, help you draft a leave request, and answer questions about attendance and payroll. What would you like to do?",
    },
  ]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [rateLimitUntil, setRateLimitUntil] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [draft, setDraft] = useState<SmartLeave | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, thinking, draft]);

  useEffect(() => {
    if (rateLimitUntil <= Date.now()) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [rateLimitUntil]);

  const secondsLeft = Math.max(0, Math.ceil((rateLimitUntil - now) / 1000));
  const limited = secondsLeft > 0;

  const send = async (text: string) => {
    const message = text.trim();
    if (!message || thinking || limited) return;

    setInput("");
    setDraft(null);
    setMessages((prev) => [
      ...prev,
      { id: nextId++, role: "user", text: message },
    ]);
    setThinking(true);

    try {
      const res = await api<ChatResponse>("/api/ai/chat", {
        method: "POST",
        body: { message },
        timeoutMs: 20000,
      });

      const reply: Message = {
        id: nextId++,
        role: "assistant",
        kind: "ai",
        text: res?.reply ?? "I could not generate a reply.",
        provider: res?.provider,
        tools: res?.tool_calls ?? [],
        smartLeave: res?.smart_leave,
      };
      setMessages((prev) => [...prev, reply]);
      if (res?.smart_leave) {
        setDraft(res.smart_leave);
      }
      if (res?.provider === "offline") {
        // Labelled honestly: the backend fell back to deterministic rules.
        toast({ type: "info", message: "Assistant is in offline rules mode." });
      }
    } catch (err) {
      const apiErr = err instanceof ApiError ? err : null;
      if (apiErr?.status === 429) {
        setRateLimitUntil(Date.now() + 60_000);
        setNow(Date.now());
        setMessages((prev) => [
          ...prev,
          {
            id: nextId++,
            role: "assistant",
            kind: "fallback",
            text: "You've hit the assistant's hourly limit. Please wait a moment — you can ask again in 60 seconds.",
          },
        ]);
      } else if (apiErr?.status === 0 && /timed out/i.test(apiErr.message)) {
        setMessages((prev) => [
          ...prev,
          {
            id: nextId++,
            role: "assistant",
            kind: "fallback",
            text: "That took too long and the assistant timed out. Please try again — shorter questions usually answer faster.",
          },
        ]);
      } else {
        setMessages((prev) => [
          ...prev,
          {
            id: nextId++,
            role: "assistant",
            kind: "error",
            text: errorMessage(err),
          },
        ]);
      }
    } finally {
      setThinking(false);
    }
  };

  const submitDraft = (workingDays: number) => {
    setMessages((prev) => [
      ...prev,
      {
        id: nextId++,
        role: "assistant",
        kind: "system",
        text: `Leave request submitted (${workingDays} working day${workingDays === 1 ? "" : "s"}). It now appears in your leave list as pending.`,
      },
    ]);
    setDraft(null);
  };

  return (
    <div className="space-y-4">
      <Card
        title="AI Assistant"
        description="Answers are AI-generated and may be wrong — confirm before acting. Tools run with your permissions only."
        bodyClassName="p-0"
      >
        <div className="max-h-[55vh] min-h-[320px] space-y-4 overflow-y-auto px-5 py-5">
          {messages.map((m) => (
            <div key={m.id} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
              <div
                className={
                  m.role === "user"
                    ? "max-w-[85%] rounded-2xl rounded-br-sm bg-accent px-4 py-2.5 text-sm text-accent-ink"
                    : m.kind === "error"
                      ? "max-w-[85%] rounded-2xl rounded-bl-sm border border-danger/40 bg-danger/10 px-4 py-2.5 text-sm text-danger"
                      : m.kind === "fallback"
                        ? "max-w-[85%] rounded-2xl rounded-bl-sm border border-warning/40 bg-warning/10 px-4 py-2.5 text-sm text-warning"
                        : m.kind === "system"
                          ? "max-w-[85%] rounded-2xl rounded-bl-sm border border-success/40 bg-success/10 px-4 py-2.5 text-sm text-success"
                          : "max-w-[85%] rounded-2xl rounded-bl-sm border border-border bg-surface-2 px-4 py-2.5 text-sm text-text"
                }
              >
                {m.role === "assistant" && m.kind === "ai" && (
                  <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-accent">
                      AI-generated
                    </span>
                    <Badge tone={m.provider === "offline" ? "warn" : "neutral"}>
                      {m.provider === "offline" ? "Offline rules mode" : m.provider === "llm" ? "LLM" : "Assistant"}
                    </Badge>
                  </div>
                )}
                <p className="whitespace-pre-wrap leading-relaxed">{m.text}</p>

                {m.tools && m.tools.length > 0 && (
                  <ul className="mt-3 space-y-1.5 border-t border-border pt-2.5">
                    {m.tools.map((t, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-muted">
                        <Icon name="check" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" />
                        <span>
                          <code className="rounded bg-surface-3 px-1 py-0.5 text-[11px] text-text">
                            {t.tool}
                          </code>
                          {t.result_summary ? ` — ${t.result_summary}` : ""}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}

                {m.role === "assistant" && m.kind === "ai" && !m.smartLeave && (
                  <p className="mt-2 text-[10px] text-muted/70">Generated by AI — verify important details.</p>
                )}
              </div>
            </div>
          ))}

          {thinking && (
            <div className="flex justify-start">
              <div className="flex items-center gap-1.5 rounded-2xl rounded-bl-sm border border-border bg-surface-2 px-4 py-3">
                <span className="h-2 w-2 animate-bounce rounded-full bg-accent [animation-delay:-0.2s]" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-accent [animation-delay:-0.1s]" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-accent" />
                <span className="ml-1 text-xs text-muted">Assistant is thinking…</span>
              </div>
            </div>
          )}

          {draft && (
            <div className="flex justify-start">
              <div className="w-full max-w-lg">
                <SmartLeaveCard
                  key={`${draft.start}-${draft.end}`}
                  initial={draft}
                  onSubmitted={submitDraft}
                  onDiscard={() => {
                    setDraft(null);
                    setMessages((prev) => [
                      ...prev,
                      {
                        id: nextId++,
                        role: "assistant",
                        kind: "system",
                        text: "Draft discarded — nothing was submitted.",
                      },
                    ]);
                  }}
                />
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        <div className="border-t border-border p-4">
          {limited && (
            <p className="mb-2 text-xs text-warning" role="status">
              Rate limit reached — the assistant is available again in {secondsLeft}s.
            </p>
          )}
          <div className="flex flex-wrap gap-1.5 pb-3">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => void send(s)}
                disabled={thinking || limited}
                className="rounded-full border border-border bg-surface-2 px-3 py-1.5 text-xs text-muted transition-colors hover:border-accent/50 hover:text-text disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                {s}
              </button>
            ))}
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void send(input);
            }}
            className="flex items-end gap-2"
          >
            <label htmlFor="chat-input" className="sr-only">
              Message the assistant
            </label>
            <Textarea
              id="chat-input"
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send(input);
                }
              }}
              placeholder={limited ? `Wait ${secondsLeft}s to ask again…` : "Ask about leave, attendance or payroll…"}
              className="min-h-[44px] resize-none"
            />
            <Button type="submit" disabled={thinking || limited || !input.trim()}>
              <Icon name="send" className="h-4 w-4" /> Send
            </Button>
          </form>
        </div>
      </Card>

      <Card title="What the assistant can do">
        <ul className="grid gap-2 text-sm text-muted sm:grid-cols-2">
          <li>• Explain your leave balance and policy</li>
          <li>• Draft a leave request for you to confirm</li>
          <li>• Summarise today&apos;s attendance status</li>
          <li>• Point you to payroll and payslips</li>
        </ul>
        <p className="mt-3 text-xs text-muted">
          The assistant cannot approve leave or change records — every action stays behind your
          confirmation.
        </p>
      </Card>
    </div>
  );
}
