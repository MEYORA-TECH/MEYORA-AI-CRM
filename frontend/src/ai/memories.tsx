import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain, Check, Lock, Pencil, Pin, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog, Modal } from "@/components/ui/overlay";
import { Badge, Button, EmptyState, Field, IconButton, Select, Skeleton, Textarea, type Tint } from "@/components/ui/primitives";
import { cn, label, relative } from "@/lib/format";
import { api, describeError } from "@/services/api";
import { useAuth, useCan } from "@/stores/auth";
import type { components } from "@/types/api";
import type { Page } from "@/types";

export type Memory = components["schemas"]["MemoryOut"];
type Link = { company_id?: string; contact_id?: string; deal_id?: string };

const TYPE_TINT: Record<string, Tint> = {
  fact: "slate", preference: "violet", requirement: "amber", relationship: "sky", decision: "emerald",
};
const SOURCE: Record<string, string> = { manual: "Added by hand", chat: "From a chat", note: "From a note", activity: "From an activity" };

export function useMemories(params: Record<string, string | undefined>) {
  return useQuery({
    queryKey: ["memories", params],
    queryFn: () => api.get<Page<Memory>>("/memories", { page_size: 50, ...params }),
  });
}

function useMemoryMutations() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ["memories"] });
  return {
    create: useMutation({
      mutationFn: (body: Record<string, unknown>) => api.post<Memory>("/memories", body),
      onSuccess: () => { done(); toast.success("Memory saved"); },
      onError: (e) => toast.error(describeError(e)),
    }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) => api.patch<Memory>(`/memories/${id}`, body),
      onSuccess: done,
      onError: (e) => toast.error(describeError(e)),
    }),
    remove: useMutation({
      mutationFn: (id: string) => api.delete(`/memories/${id}`),
      onSuccess: () => { done(); toast.success("Memory deleted"); },
      onError: (e) => toast.error(describeError(e)),
    }),
  };
}

/** Add or edit one memory. */
function MemoryEditor({ open, onOpenChange, memory, link }: {
  open: boolean; onOpenChange: (o: boolean) => void; memory?: Memory; link?: Link;
}) {
  const { create, update } = useMemoryMutations();
  const [content, setContent] = useState(memory?.content ?? "");
  const [type, setType] = useState(memory?.memory_type ?? "fact");
  const [personal, setPersonal] = useState(false);
  const saving = create.isPending || update.isPending;

  const save = async () => {
    if (memory) await update.mutateAsync({ id: memory.id, body: { content, memory_type: type } });
    else await create.mutateAsync({ content, memory_type: type, personal, ...link });
    onOpenChange(false);
  };

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={memory ? "Edit memory" : "Add a memory"}
      description="A durable fact the assistant should know, written as one clear sentence."
      footer={<><Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button><Button variant="primary" loading={saving} disabled={content.trim().length < 5} onClick={save}>Save memory</Button></>}
    >
      <div className="flex flex-col gap-4">
        <Field label="Memory" htmlFor="memory-content">
          <Textarea id="memory-content" autoFocus value={content} onChange={(e) => setContent(e.target.value)}
            placeholder="ABC Manufacturing prefers private (on-premise) deployment." />
        </Field>
        <Field label="Kind" htmlFor="memory-type">
          <Select id="memory-type" value={type} onChange={(e) => setType(e.target.value)}>
            {Object.keys(TYPE_TINT).map((t) => <option key={t} value={t}>{label(t)}</option>)}
          </Select>
        </Field>
        {!memory && !link ? (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={personal} onChange={(e) => setPersonal(e.target.checked)} className="size-4 accent-[var(--jade)]" />
            Only for me (a personal preference)
          </label>
        ) : null}
      </div>
    </Modal>
  );
}

export function MemoryRow({ m }: { m: Memory }) {
  const me = useAuth((s) => s.me);
  const canManage = useCan("crm:delete");
  const canWrite = useCan("crm:write");
  const { update, remove } = useMemoryMutations();
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const mine = m.user_id === me?.id;
  const canChange = canWrite && (mine || canManage);

  return (
    <li className={cn("flex items-start gap-3 px-5 py-3.5", m.status === "superseded" && "opacity-55")}>
      <span className={cn("mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-xl", m.scope === "user" ? "bg-tint-violet" : "bg-jade-soft text-jade")}>
        {m.scope === "user" ? <Lock className="size-4" /> : <Brain className="size-4" />}
      </span>
      <div className="min-w-0 flex-1">
        <p className={cn("text-sm text-ink", m.status === "superseded" && "line-through")}>{m.content}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-3">
          <Badge tint={TYPE_TINT[m.memory_type] ?? "slate"} className="h-5 px-2 text-[10px]">{label(m.memory_type)}</Badge>
          {m.status === "pending_review" ? <Badge tint="amber" className="h-5 px-2 text-[10px]">Needs review</Badge> : null}
          {m.status === "superseded" ? <Badge className="h-5 px-2 text-[10px]">Replaced</Badge> : null}
          {m.importance >= 5 ? <Badge tint="jade" className="h-5 px-2 text-[10px]">Pinned</Badge> : null}
          <span>{SOURCE[m.source_type] ?? label(m.source_type)}{m.created_by === "ai" ? " · saved by AI" : ""} · {relative(m.created_at)}</span>
          {m.created_by === "ai" && m.status !== "superseded" ? <span className="num">· {Math.round(m.confidence * 100)}% sure</span> : null}
        </div>
      </div>
      {canChange && m.status !== "superseded" ? (
        <div className="flex shrink-0 items-center">
          {m.status === "pending_review" ? (
            <IconButton label="Approve memory" onClick={() => update.mutate({ id: m.id, body: { status: "active" } })}><Check className="size-4 text-jade" /></IconButton>
          ) : null}
          <IconButton label={m.importance >= 5 ? "Unpin" : "Pin"} onClick={() => update.mutate({ id: m.id, body: { importance: m.importance >= 5 ? 3 : 5 } })}>
            <Pin className={cn("size-4", m.importance >= 5 && "fill-current text-jade")} />
          </IconButton>
          <IconButton label="Edit memory" onClick={() => setEditing(true)}><Pencil className="size-4" /></IconButton>
          <IconButton label="Delete memory" onClick={() => setDeleting(true)}><Trash2 className="size-4" /></IconButton>
        </div>
      ) : null}
      {editing ? <MemoryEditor open={editing} onOpenChange={setEditing} memory={m} /> : null}
      <ConfirmDialog open={deleting} onOpenChange={setDeleting} title="Delete this memory?"
        description="The assistant will forget it completely. This can't be undone." confirmLabel="Delete memory"
        loading={remove.isPending} onConfirm={async () => { await remove.mutateAsync(m.id); setDeleting(false); }} />
    </li>
  );
}

export function MemoryList({ items, loading, empty }: { items?: Memory[]; loading: boolean; empty: React.ReactNode }) {
  if (loading) return <div className="space-y-3 p-5">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div>;
  if (!items?.length) return <>{empty}</>;
  return <ul className="divide-y divide-[var(--line)]">{items.map((m) => <MemoryRow key={m.id} m={m} />)}</ul>;
}

export function AddMemoryButton({ link, size = "sm" }: { link?: Link; size?: "sm" | "md" }) {
  const [open, setOpen] = useState(false);
  const canWrite = useCan("crm:write");
  if (!canWrite) return null;
  return (
    <>
      <Button size={size} icon={<Brain className="size-4" />} onClick={() => setOpen(true)}>Add memory</Button>
      {open ? <MemoryEditor open={open} onOpenChange={setOpen} link={link} /> : null}
    </>
  );
}

/** "AI memory" tab on a company, contact or deal. */
export function RecordMemoryPanel({ field, id }: { field: "company_id" | "contact_id" | "deal_id"; id: string }) {
  const list = useMemories({ [field]: id });
  return (
    <div>
      <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
        <p className="text-xs text-ink-3">What the assistant remembers about this record. Edit or delete anything that's wrong.</p>
        <AddMemoryButton link={{ [field]: id }} />
      </div>
      <MemoryList
        items={list.data?.items}
        loading={list.isLoading}
        empty={<EmptyState icon={<Brain className="size-5" />} title="Nothing remembered yet"
          body="Memories come from notes, from chats (“remember that…”), or from you adding them here." />}
      />
    </div>
  );
}
