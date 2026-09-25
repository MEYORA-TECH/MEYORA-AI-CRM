import { CalendarPlus, CheckSquare, Handshake, Plus, StickyNote, UsersRound } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Badge, Button, EmptyState, Skeleton, Textarea } from "@/components/ui/primitives";
import { activities, deals, notes, tasks, contacts, useMembers } from "@/hooks/resources";
import { cn, dateTime, money, relative } from "@/lib/format";
import { DEAL_STATUS, TASK_PRIORITY } from "@/lib/status";
import { ACTIVITY_FIELDS, TASK_FIELDS } from "@/pages/fields";
import { useAuth, useCan } from "@/stores/auth";
import { EntityForm } from "./EntityForm";

export type LinkField = "company_id" | "contact_id" | "lead_id" | "deal_id";

function Rows({ loading, children }: { loading: boolean; children: React.ReactNode }) {
  if (loading) return <div className="space-y-3 p-5">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-10" />)}</div>;
  return <ul className="divide-y divide-[var(--line)]">{children}</ul>;
}

function PanelBar({ children }: { children: React.ReactNode }) {
  return <div className="flex items-center justify-end gap-2 border-b border-line px-4 py-2.5">{children}</div>;
}

/* ---------- Notes ---------- */

export function NotesPanel({ field, id }: { field: LinkField; id: string }) {
  const list = notes.useList({ [field]: id, page_size: 50 });
  const create = notes.useCreate();
  const canWrite = useCan("crm:write");
  const members = useMembers();
  const [body, setBody] = useState("");
  const author = (uid: string | null) => members.data?.find((m) => m.user.id === uid)?.user.full_name ?? "Someone";

  return (
    <div>
      {canWrite ? (
        <form
          className="flex flex-col gap-2 border-b border-line p-4"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!body.trim()) return;
            await create.mutateAsync({ body: body.trim(), [field]: id } as never);
            setBody("");
          }}
        >
          <Textarea value={body} onChange={(e) => setBody(e.target.value)} placeholder="Write a note…" aria-label="New note" className="min-h-20" />
          <div className="flex justify-end">
            <Button size="sm" variant="primary" type="submit" loading={create.isPending} disabled={!body.trim()}>Add note</Button>
          </div>
        </form>
      ) : null}
      <Rows loading={list.isLoading}>
        {list.data?.items.length ? (
          list.data.items.map((n) => (
            <li key={n.id} className="px-5 py-3.5">
              <p className="text-sm whitespace-pre-line text-ink">{n.body}</p>
              <p className="mt-1.5 text-xs text-ink-3">{author(n.author_id)} · {relative(n.created_at)}</p>
            </li>
          ))
        ) : (
          <EmptyState icon={<StickyNote className="size-5" />} title="No notes yet" body="Capture requirements, preferences and decisions here." />
        )}
      </Rows>
    </div>
  );
}

/* ---------- Tasks ---------- */

export function TasksPanel({ field, id }: { field: LinkField; id: string }) {
  const list = tasks.useList({ [field]: id, page_size: 50, sort: "due_at" });
  const create = tasks.useCreate();
  const update = tasks.useUpdate();
  const canWrite = useCan("crm:write");
  const [open, setOpen] = useState(false);

  return (
    <div>
      {canWrite ? (
        <PanelBar>
          <Button size="sm" icon={<Plus className="size-4" />} onClick={() => setOpen(true)}>New task</Button>
        </PanelBar>
      ) : null}
      <Rows loading={list.isLoading}>
        {list.data?.items.length ? (
          list.data.items.map((t) => {
            const done = t.status === "completed";
            const overdue = !done && t.due_at && new Date(t.due_at) < new Date();
            return (
              <li key={t.id} className="flex items-center gap-3 px-5 py-3">
                <input
                  type="checkbox"
                  checked={done}
                  disabled={!canWrite}
                  aria-label={done ? `Mark “${t.title}” as not done` : `Complete “${t.title}”`}
                  onChange={() => update.mutate({ id: t.id, input: { status: done ? "todo" : "completed" } })}
                  className="size-4 accent-[var(--jade)]"
                />
                <div className="min-w-0 flex-1">
                  <p className={cn("truncate text-sm font-medium", done && "text-ink-3 line-through")}>{t.title}</p>
                  <p className={cn("text-xs", overdue ? "font-semibold text-danger" : "text-ink-3")}>
                    {t.due_at ? `Due ${dateTime(t.due_at)}` : "No due date"}
                  </p>
                </div>
                <Badge tint={TASK_PRIORITY[t.priority].tint}>{TASK_PRIORITY[t.priority].label}</Badge>
              </li>
            );
          })
        ) : (
          <EmptyState icon={<CheckSquare className="size-5" />} title="No tasks" body="Create a follow-up so nothing slips." />
        )}
      </Rows>
      <EntityForm
        open={open}
        onOpenChange={setOpen}
        title="New task"
        fields={TASK_FIELDS.filter((f) => !["company_id", "contact_id", "deal_id", "lead_id", "status"].includes(f.name))}
        submitLabel="Create task"
        saving={create.isPending}
        onSubmit={(v) => create.mutateAsync({ ...v, [field]: id } as never)}
      />
    </div>
  );
}

/* ---------- Activities ---------- */

export function LogActivityButton({ link }: { link?: Partial<Record<LinkField, string>> }) {
  const create = activities.useCreate();
  const [open, setOpen] = useState(false);
  const canWrite = useCan("crm:write");
  if (!canWrite) return null;
  const linked = Object.keys(link ?? {});
  return (
    <>
      <Button icon={<CalendarPlus className="size-4" />} onClick={() => setOpen(true)}>Log activity</Button>
      <EntityForm
        open={open}
        onOpenChange={setOpen}
        title="Log activity"
        description="Record a call, meeting, email or follow-up."
        fields={ACTIVITY_FIELDS.filter((f) => !linked.includes(f.name))}
        initial={undefined}
        submitLabel="Log activity"
        saving={create.isPending}
        onSubmit={(v) => create.mutateAsync({ type: "call", ...v, ...link } as never)}
      />
    </>
  );
}

/* ---------- Related deals & contacts ---------- */

export function DealsPanel({ filter }: { filter: Record<string, string> }) {
  const list = deals.useList({ ...filter, page_size: 50 });
  return (
    <Rows loading={list.isLoading}>
      {list.data?.items.length ? (
        list.data.items.map((d) => (
          <li key={d.id}>
            <Link to={`/deals/${d.id}`} className="focus-ring flex items-center gap-3 px-5 py-3 hover:bg-[var(--glass-2)]">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{d.name}</p>
                <p className="text-xs text-ink-3">{d.expected_close_date ? `Closes ${d.expected_close_date}` : "No close date"}</p>
              </div>
              <span className="num text-sm font-semibold">{money(d.amount, d.currency)}</span>
              <Badge tint={DEAL_STATUS[d.status].tint}>{DEAL_STATUS[d.status].label}</Badge>
            </Link>
          </li>
        ))
      ) : (
        <EmptyState icon={<Handshake className="size-5" />} title="No deals" body="Deals linked to this record will show here." />
      )}
    </Rows>
  );
}

export function ContactsPanel({ companyId }: { companyId: string }) {
  const list = contacts.useList({ company_id: companyId, page_size: 50, sort: "first_name" });
  return (
    <Rows loading={list.isLoading}>
      {list.data?.items.length ? (
        list.data.items.map((c) => (
          <li key={c.id}>
            <Link to={`/contacts/${c.id}`} className="focus-ring flex items-center gap-3 px-5 py-3 hover:bg-[var(--glass-2)]">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{c.full_name}</p>
                <p className="truncate text-xs text-ink-3">{[c.job_title, c.email].filter(Boolean).join(" · ") || "—"}</p>
              </div>
            </Link>
          </li>
        ))
      ) : (
        <EmptyState icon={<UsersRound className="size-5" />} title="No contacts" body="Add people at this company to track conversations." />
      )}
    </Rows>
  );
}

export function useCurrentUserId() {
  return useAuth((s) => s.me?.id);
}
