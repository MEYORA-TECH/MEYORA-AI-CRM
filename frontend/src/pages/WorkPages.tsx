/** Activities and Tasks: cross-record work lists. */
import { createColumnHelper } from "@tanstack/react-table";
import { CalendarRange, CheckSquare, Plus } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { DataTable } from "@/components/data/DataTable";
import { EntityForm } from "@/components/data/EntityForm";
import { EntityName } from "@/components/data/EntityPicker";
import { LogActivityButton } from "@/components/data/Related";
import { ConfirmDialog } from "@/components/ui/overlay";
import { Badge, Button, EmptyState, ErrorState, Select } from "@/components/ui/primitives";
import { activities, tasks } from "@/hooks/resources";
import { PageHeader } from "@/layouts/AppShell";
import { cn, dateTime, label, relative, timeZone } from "@/lib/format";
import { ACTIVITY_TYPES, TASK_PRIORITY, TASK_STATUS } from "@/lib/status";
import { describeError } from "@/services/api";
import { useCan } from "@/stores/auth";
import type { Activity, Task } from "@/types";
import { ACTIVITY_FIELDS, TASK_FIELDS } from "./fields";

function usePaging() {
  const [params, setParams] = useSearchParams();
  const set = (patch: Record<string, string | undefined>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) v ? next.set(k, v) : next.delete(k);
    if (!("page" in patch)) next.delete("page");
    setParams(next, { replace: true });
  };
  return { params, set, page: Number(params.get("page") ?? 1), sort: params.get("sort") ?? undefined };
}

function Related({ row }: { row: Activity | Task }) {
  const parts: [string | null, "company" | "contact" | "deal" | "lead"][] = [
    [row.company_id, "company"], [row.contact_id, "contact"], [row.deal_id, "deal"], [row.lead_id, "lead"],
  ];
  const linked = parts.filter(([id]) => id);
  if (!linked.length) return <span className="text-ink-3">—</span>;
  return (
    <span className="flex flex-wrap gap-x-2 text-ink-2">
      {linked.map(([id, kind]) => <span key={kind} className="truncate"><EntityName kind={kind} id={id} /></span>)}
    </span>
  );
}

/* ---------------- Activities ---------------- */

const acol = createColumnHelper<Activity>();

export function ActivitiesPage() {
  const { params, set, page, sort } = usePaging();
  const type = params.get("type") ?? "";
  const list = activities.useList({ page, page_size: 25, sort, type: type || undefined });
  const update = activities.useUpdate();
  const [editing, setEditing] = useState<Activity | null>(null);

  const columns = [
    acol.accessor("subject", {
      header: "Activity",
      cell: (c) => (
        <div className="min-w-0">
          <p className="truncate font-semibold">{c.getValue()}</p>
          <p className="truncate text-xs text-ink-3">{c.row.original.outcome ?? c.row.original.body ?? ""}</p>
        </div>
      ),
    }),
    acol.accessor("type", { header: "Type", meta: { sortKey: "type" }, cell: (c) => <Badge tint="violet">{label(c.getValue())}</Badge> }),
    acol.accessor("status", {
      header: "Status",
      meta: { sortKey: "status" },
      cell: (c) => <Badge tint={c.getValue() === "planned" ? "sky" : c.getValue() === "completed" ? "emerald" : "slate"}>{label(c.getValue())}</Badge>,
    }),
    acol.display({ id: "related", header: "Related to", cell: (c) => <Related row={c.row.original} /> }),
    acol.accessor("actor_id", { header: "By", cell: (c) => <EntityName kind="member" id={c.getValue()} /> }),
    acol.accessor("occurred_at", {
      header: "When",
      meta: { sortKey: "occurred_at", align: "right" },
      cell: (c) => <span className="text-ink-2" title={dateTime(c.getValue())}>{relative(c.getValue())}</span>,
    }),
  ];

  return (
    <>
      <PageHeader title="Activities" description="Calls, meetings, emails and follow-ups across every record." actions={<LogActivityButton />} />
      <div className="rise mb-3 flex gap-2">
        <Select aria-label="Type" value={type} onChange={(e) => set({ type: e.target.value || undefined })} className="w-auto min-w-40">
          <option value="">Type: all</option>
          {[...ACTIVITY_TYPES, { value: "stage_change", label: "Stage change" }, { value: "system", label: "System" }].map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </Select>
      </div>
      {list.error ? (
        <ErrorState message={describeError(list.error)} onRetry={() => list.refetch()} />
      ) : (
        <DataTable
          columns={columns}
          rows={list.data?.items}
          total={list.data?.total ?? 0}
          page={page}
          pageSize={25}
          onPageChange={(p) => set({ page: String(p) })}
          sort={sort}
          onSortChange={(s) => set({ sort: s })}
          loading={list.isLoading}
          onRowClick={(row) => (row.type === "stage_change" || row.type === "system" ? undefined : setEditing(row))}
          empty={<EmptyState icon={<CalendarRange className="size-5" />} title="No activities yet" body="Log a call or meeting to start building each account's history." />}
        />
      )}
      <EntityForm
        open={Boolean(editing)}
        onOpenChange={(o) => !o && setEditing(null)}
        title="Edit activity"
        fields={ACTIVITY_FIELDS}
        initial={editing ?? undefined}
        submitLabel="Save changes"
        saving={update.isPending}
        onSubmit={(input) => update.mutateAsync({ id: editing!.id, input })}
      />
    </>
  );
}

/* ---------------- Tasks ---------------- */

const tcol = createColumnHelper<Task>();
const DUE_VIEWS = [
  { value: "", label: "All" },
  { value: "overdue", label: "Overdue" },
  { value: "today", label: "Today" },
  { value: "upcoming", label: "Upcoming" },
];

export function TasksPage() {
  const { params, set, page, sort } = usePaging();
  const due = params.get("due") ?? "";
  const mine = params.get("assignee") !== "any";
  const status = params.get("status") ?? "";
  const list = tasks.useList({
    page, page_size: 25, sort: sort ?? "due_at", due: due || undefined, assignee: mine ? "me" : undefined,
    status: status ? [status] : ["todo", "in_progress"], tz: timeZone(),
  });
  const create = tasks.useCreate();
  const update = tasks.useUpdate();
  const remove = tasks.useDelete();
  const canWrite = useCan("crm:write");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Task | null>(null);
  const [deleting, setDeleting] = useState<Task | null>(null);

  const columns = [
    tcol.display({
      id: "done",
      header: () => <span className="sr-only">Done</span>,
      meta: { className: "w-10" },
      cell: (c) => {
        const t = c.row.original;
        const done = t.status === "completed";
        return (
          <input
            type="checkbox"
            checked={done}
            disabled={!canWrite}
            onClick={(e) => e.stopPropagation()}
            onChange={() => update.mutate({ id: t.id, input: { status: done ? "todo" : "completed" } })}
            aria-label={done ? `Mark “${t.title}” as not done` : `Complete “${t.title}”`}
            className="size-4 accent-[var(--jade)]"
          />
        );
      },
    }),
    tcol.accessor("title", {
      header: "Task",
      meta: { sortKey: "title" },
      cell: (c) => <p className={cn("font-semibold", c.row.original.status === "completed" && "text-ink-3 line-through")}>{c.getValue()}</p>,
    }),
    tcol.accessor("priority", {
      header: "Priority",
      meta: { sortKey: "priority" },
      cell: (c) => <Badge tint={TASK_PRIORITY[c.getValue()].tint}>{TASK_PRIORITY[c.getValue()].label}</Badge>,
    }),
    tcol.accessor("status", { header: "Status", cell: (c) => <Badge tint={TASK_STATUS[c.getValue()].tint}>{TASK_STATUS[c.getValue()].label}</Badge> }),
    tcol.display({ id: "related", header: "Related to", cell: (c) => <Related row={c.row.original} /> }),
    tcol.accessor("assignee_id", { header: "Assignee", cell: (c) => <EntityName kind="member" id={c.getValue()} /> }),
    tcol.accessor("due_at", {
      header: "Due",
      meta: { sortKey: "due_at", align: "right" },
      cell: (c) => {
        const t = c.row.original;
        const overdue = t.status !== "completed" && t.due_at && new Date(t.due_at) < new Date();
        return <span className={cn(overdue ? "font-semibold text-danger" : "text-ink-2")}>{t.due_at ? dateTime(t.due_at) : "—"}</span>;
      },
    }),
  ];

  return (
    <>
      <PageHeader
        title="Tasks"
        description={mine ? "What's on your plate, soonest first." : "Everyone's open work."}
        actions={canWrite ? <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>New task</Button> : null}
      />
      <div className="rise mb-3 flex flex-wrap items-center gap-2">
        <div className="glass-soft flex gap-1 rounded-full p-1" role="group" aria-label="Due">
          {DUE_VIEWS.map((v) => (
            <button
              key={v.value}
              onClick={() => set({ due: v.value || undefined })}
              aria-pressed={due === v.value}
              className={cn("focus-ring h-8 rounded-full px-3.5 text-[13px] font-semibold text-ink-2", due === v.value && "bg-[var(--ink)] text-[var(--canvas)]")}
            >
              {v.label}
            </button>
          ))}
        </div>
        <Select aria-label="Assignee" value={mine ? "me" : "any"} onChange={(e) => set({ assignee: e.target.value === "any" ? "any" : undefined })} className="w-auto">
          <option value="me">Assigned to me</option>
          <option value="any">Everyone</option>
        </Select>
        <Select aria-label="Status" value={status} onChange={(e) => set({ status: e.target.value || undefined })} className="w-auto">
          <option value="">Open tasks</option>
          {Object.entries(TASK_STATUS).map(([v, s]) => <option key={v} value={v}>{s.label}</option>)}
        </Select>
      </div>
      {list.error ? (
        <ErrorState message={describeError(list.error)} onRetry={() => list.refetch()} />
      ) : (
        <DataTable
          columns={columns}
          rows={list.data?.items}
          total={list.data?.total ?? 0}
          page={page}
          pageSize={25}
          onPageChange={(p) => set({ page: String(p) })}
          sort={sort ?? "due_at"}
          onSortChange={(s) => set({ sort: s })}
          loading={list.isLoading}
          onRowClick={(t) => setEditing(t)}
          empty={
            <EmptyState
              icon={<CheckSquare className="size-5" />}
              title={due === "overdue" ? "Nothing overdue" : "No tasks here"}
              body={due === "overdue" ? "You're caught up." : "Create a task, or add one from any company, contact, lead or deal."}
            />
          }
        />
      )}
      <EntityForm open={creating} onOpenChange={setCreating} title="New task" fields={TASK_FIELDS.filter((f) => f.name !== "status")}
        submitLabel="Create task" saving={create.isPending} onSubmit={(v) => create.mutateAsync(v as never)} />
      <EntityForm
        open={Boolean(editing)}
        onOpenChange={(o) => !o && setEditing(null)}
        title="Edit task"
        fields={TASK_FIELDS}
        initial={editing ?? undefined}
        submitLabel="Save changes"
        saving={update.isPending}
        onSubmit={(input) => update.mutateAsync({ id: editing!.id, input })}
        footerStart={
          canWrite ? (
            <Button variant="ghost" className="text-danger" onClick={() => { setDeleting(editing); setEditing(null); }}>
              Delete task
            </Button>
          ) : undefined
        }
      />
      <ConfirmDialog
        open={Boolean(deleting)}
        onOpenChange={(o) => !o && setDeleting(null)}
        title="Delete this task?"
        description={deleting ? `“${deleting.title}” will be removed permanently.` : ""}
        confirmLabel="Delete task"
        loading={remove.isPending}
        onConfirm={async () => {
          await remove.mutateAsync(deleting!.id);
          setDeleting(null);
        }}
      />
    </>
  );
}
