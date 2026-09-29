import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, Copy, ExternalLink, Linkedin, Mail, ShieldCheck, X } from "@/components/icons";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { create } from "zustand";

import { Badge, Button, Input, Textarea } from "@/components/ui/primitives";
import { cn } from "@/lib/format";
import { api, describeError } from "@/services/api";

export interface ActionUi {
  kind: "action";
  id: string;
  ref: string;
  status: "proposed" | "executed" | "rejected" | "failed" | "expired";
  title: string;
  summary: string;
  variant: "crm" | "email" | "linkedin";
  changes: { field: string; old: unknown; new: unknown }[];
  target: { type: string | null; id: string | null; label: string | null; href: string | null };
  email?: { to: string[]; subject: string; body: string; can_send: boolean; from: string | null } | null;
  linkedin?: {
    kind: "connection_note" | "message" | "inmail";
    label: string;
    text: string;
    subject: string | null;
    limit: number;
    profile_url: string | null;
    recipient: string;
  } | null;
  result?: { summary: string; href: string | null } | null;
  error?: string | null;
}

interface ActionResponse {
  id: string;
  status: ActionUi["status"];
  result: ActionUi["result"];
  error: string | null;
}

/** Live status per action, shared so "Confirm all" and individual cards stay in sync. */
const useActionState = create<{ byId: Record<string, Partial<ActionUi>>; set: (id: string, s: Partial<ActionUi>) => void }>(
  (set) => ({ byId: {}, set: (id, s) => set((st) => ({ byId: { ...st.byId, [id]: { ...st.byId[id], ...s } } })) }),
);

export function useLiveAction(ui: ActionUi): ActionUi {
  const live = useActionState((s) => s.byId[ui.id]);
  return { ...ui, ...live };
}

function useRefreshAfterAction() {
  const qc = useQueryClient();
  return () => {
    for (const key of ["/tasks", "/deals", "/leads", "/contacts", "/companies", "/notes", "/activities", "timeline", "dashboard", "emails"]) {
      qc.invalidateQueries({ queryKey: [key] });
    }
  };
}

function apply(res: ActionResponse) {
  useActionState.getState().set(res.id, { status: res.status, result: res.result, error: res.error });
  if (res.status === "executed") toast.success(res.result?.summary ?? "Done");
  else if (res.status !== "rejected") toast.error(res.error ?? `Action ${res.status}`);
}

const show = (v: unknown) => (v === null || v === undefined || v === "" ? "—" : String(v));

const STATUS: Record<ActionUi["status"], { label: string; tint: "sky" | "emerald" | "slate" | "rose" | "amber" }> = {
  proposed: { label: "Waiting for you", tint: "sky" },
  executed: { label: "Done", tint: "emerald" },
  rejected: { label: "Cancelled", tint: "slate" },
  failed: { label: "Didn't work", tint: "rose" },
  expired: { label: "Expired", tint: "amber" },
};

export function ActionCard({ ui: raw }: { ui: ActionUi }) {
  const ui = useLiveAction(raw);
  const refresh = useRefreshAfterAction();
  const [busy, setBusy] = useState<"confirm" | "reject" | null>(null);
  const [draft, setDraft] = useState(() => ({
    to: ui.email?.to.join(", ") ?? "", subject: ui.email?.subject ?? "", body: ui.email?.body ?? "",
    text: ui.linkedin?.text ?? "",
  }));
  const overLimit = ui.variant === "linkedin" && ui.linkedin ? draft.text.length > ui.linkedin.limit : false;
  const pending = ui.status === "proposed";
  const status = STATUS[ui.status];

  const decide = async (kind: "confirm" | "reject") => {
    setBusy(kind);
    try {
      const body = kind !== "confirm" ? undefined
        : ui.variant === "email"
          ? { edits: { to: draft.to.split(",").map((s) => s.trim()).filter(Boolean), subject: draft.subject, body: draft.body } }
          : ui.variant === "linkedin" ? { edits: { text: draft.text } } : undefined;
      apply(await api.post<ActionResponse>(`/ai/actions/${ui.id}/${kind}`, body));
      refresh();
    } catch (e) {
      toast.error(describeError(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className={cn("glass-dense overflow-hidden rounded-2xl text-sm", pending && "ring-1 ring-[var(--jade)]/40")}>
      <div className="flex items-center gap-2 border-b border-line px-3.5 py-2.5">
        {ui.variant === "email" ? <Mail className="size-4 text-jade" />
          : ui.variant === "linkedin" ? <Linkedin className="size-4 text-[#0a66c2]" />
          : <ShieldCheck className="size-4 text-jade" />}
        <span className="font-semibold">{ui.title}</span>
        {ui.target.label ? (
          ui.target.href ? <Link to={ui.target.href} className="truncate text-xs text-ink-3 hover:underline">· {ui.target.label}</Link>
          : <span className="truncate text-xs text-ink-3">· {ui.target.label}</span>
        ) : null}
        <Badge tint={status.tint} className="ml-auto h-5 px-2 text-[10px]">{status.label}</Badge>
      </div>

      {ui.variant === "email" && ui.email ? (
        <div className="space-y-2 px-3.5 py-3">
          <label className="flex items-center gap-2 text-xs text-ink-3">To
            <Input value={draft.to} disabled={!pending} onChange={(e) => setDraft({ ...draft, to: e.target.value })} className="h-8" aria-label="To" />
          </label>
          <Input value={draft.subject} disabled={!pending} onChange={(e) => setDraft({ ...draft, subject: e.target.value })} className="h-8 font-semibold" aria-label="Subject" />
          <Textarea value={draft.body} disabled={!pending} onChange={(e) => setDraft({ ...draft, body: e.target.value })} className="min-h-40 text-[13px]" aria-label="Message" />
          {ui.email.from ? <p className="text-[11px] text-ink-3">Sends from {ui.email.from}</p> : null}
        </div>
      ) : ui.variant === "linkedin" && ui.linkedin ? (
        <div className="space-y-2 px-3.5 py-3">
          <p className="text-[11px] text-ink-3">
            Nila can't send on LinkedIn. Copy this, send it there, then log it here.
          </p>
          {ui.linkedin.subject ? <p className="text-[13px] font-semibold">{ui.linkedin.subject}</p> : null}
          <Textarea value={draft.text} disabled={!pending} onChange={(e) => setDraft({ ...draft, text: e.target.value })}
            className="min-h-28 text-[13px]" aria-label="LinkedIn message" />
          <p className={cn("num text-right text-[11px]", overLimit ? "font-semibold text-danger" : "text-ink-3")}>
            {draft.text.length} / {ui.linkedin.limit}{overLimit ? " · too long for a connection note" : ""}
          </p>
        </div>
      ) : (
        <dl className="divide-y divide-[var(--line)] px-3.5">
          {ui.changes.map((c) => (
            <div key={c.field} className="grid grid-cols-[92px_1fr] items-baseline gap-3 py-2">
              <dt className="text-xs text-ink-3">{c.field}</dt>
              <dd className="flex min-w-0 flex-wrap items-center gap-1.5 text-[13px]">
                {c.old !== null && c.old !== undefined ? (
                  <><span className="text-ink-3 line-through">{show(c.old)}</span><ArrowRight className="size-3 text-ink-3" /></>
                ) : null}
                <span className="font-medium text-ink">{show(c.new)}</span>
              </dd>
            </div>
          ))}
        </dl>
      )}

      {pending ? (
        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-line px-3.5 py-2.5">
          {ui.variant === "linkedin" && ui.linkedin ? (
            <>
              <Button size="sm" variant="ghost" icon={<Copy className="size-3.5" />} className="mr-auto"
                onClick={async () => { await navigator.clipboard.writeText(draft.text).catch(() => undefined); toast.success("Copied"); }}>Copy</Button>
              <a className="focus-ring inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-control)] px-3 text-[13px] font-semibold text-ink-2 hover:bg-glass-2"
                target="_blank" rel="noopener noreferrer"
                href={ui.linkedin.profile_url ?? `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(ui.linkedin.recipient)}`}>
                <ExternalLink className="size-3.5" /> {ui.linkedin.profile_url ? "Open profile" : "Find on LinkedIn"}
              </a>
            </>
          ) : null}
          {ui.variant === "email" && ui.email && !ui.email.can_send ? (
            <>
              <span className="mr-auto text-[11px] text-ink-3">Connect Gmail in Settings to send from Nila.</span>
              <Button size="sm" variant="ghost" icon={<Copy className="size-3.5" />}
                onClick={async () => { await navigator.clipboard.writeText(draft.body).catch(() => undefined); toast.success("Copied"); }}>Copy</Button>
              <a className="focus-ring inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-control)] px-3 text-[13px] font-semibold text-ink-2 hover:bg-glass-2"
                href={`mailto:${encodeURIComponent(draft.to)}?subject=${encodeURIComponent(draft.subject)}&body=${encodeURIComponent(draft.body)}`}>
                <ExternalLink className="size-3.5" /> Open in mail app
              </a>
            </>
          ) : null}
          <Button size="sm" variant="ghost" icon={<X className="size-3.5" />} loading={busy === "reject"} disabled={Boolean(busy)} onClick={() => decide("reject")}>
            Cancel
          </Button>
          <Button size="sm" variant="primary" icon={ui.variant === "email" ? <Mail className="size-3.5" /> : <Check className="size-3.5" />}
            loading={busy === "confirm"} disabled={Boolean(busy) || (ui.variant === "email" && !ui.email?.can_send) || overLimit} onClick={() => decide("confirm")}>
            {ui.variant === "email" ? "Send" : ui.variant === "linkedin" ? "Log as sent" : "Confirm"}
          </Button>
        </div>
      ) : ui.status === "executed" && ui.result ? (
        <p className="flex items-center gap-2 border-t border-line px-3.5 py-2.5 text-xs text-ink-2">
          <Check className="size-3.5 text-jade" /> {ui.result.summary}
          {ui.result.href ? <Link to={ui.result.href} className="ml-auto font-semibold text-jade hover:underline">Open</Link> : null}
        </p>
      ) : ui.error ? (
        <p className="border-t border-line px-3.5 py-2.5 text-xs font-medium text-danger">{ui.error}</p>
      ) : null}
    </div>
  );
}

/** Shown under a turn that proposed several changes. */
export function ConfirmAllBar({ actions }: { actions: ActionUi[] }) {
  const byId = useActionState((s) => s.byId);
  const refresh = useRefreshAfterAction();
  const [busy, setBusy] = useState(false);
  // Drafts (email, LinkedIn) need a person's eye one at a time; only plain CRM changes batch.
  const pending = actions.filter((a) => (byId[a.id]?.status ?? a.status) === "proposed" && a.variant === "crm");
  if (pending.length < 2) return null;
  return (
    <div className="glass-soft flex items-center justify-between gap-3 rounded-2xl px-3.5 py-2.5 text-sm">
      <span className="text-ink-2">{pending.length} changes waiting for you</span>
      <Button size="sm" variant="primary" icon={<Check className="size-3.5" />} loading={busy}
        onClick={async () => {
          setBusy(true);
          try {
            const results = await api.post<ActionResponse[]>("/ai/actions/confirm-all", { ids: pending.map((a) => a.id) });
            results.forEach(apply);
            refresh();
          } catch (e) {
            toast.error(describeError(e));
          } finally {
            setBusy(false);
          }
        }}>
        Confirm all {pending.length}
      </Button>
    </div>
  );
}
