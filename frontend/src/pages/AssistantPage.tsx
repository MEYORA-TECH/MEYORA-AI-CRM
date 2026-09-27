import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquarePlus, MoreHorizontal, Pencil, Search, Trash2 } from "@/components/icons";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Composer, Messages, UsageLine, Welcome } from "@/ai/ChatThread";
import { useAiStatus, useChat } from "@/ai/useChat";
import { ConfirmDialog, DropdownMenu, MenuItem, Modal } from "@/components/ui/overlay";
import { Button, Card, EmptyState, IconButton, Input, Skeleton } from "@/components/ui/primitives";
import { cn, relative } from "@/lib/format";
import { api, describeError } from "@/services/api";
import type { Page } from "@/types";

interface Conversation {
  id: string;
  title: string;
  provider: string | null;
  last_message_at: string;
}

/** Today / Yesterday / This week / Earlier, like a mail client. */
function groupByDay(items: Conversation[]) {
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const today = startOfDay(new Date());
  const day = 86_400_000;
  const groups: { label: string; items: Conversation[] }[] = [];
  for (const c of items) {
    const t = startOfDay(new Date(c.last_message_at));
    const label = t >= today ? "Today" : t >= today - day ? "Yesterday" : t >= today - 6 * day ? "This week" : "Earlier";
    const last = groups[groups.length - 1];
    if (last?.label === label) last.items.push(c);
    else groups.push({ label, items: [c] });
  }
  return groups;
}

function useConversations(q: string) {
  return useQuery({
    queryKey: ["ai", "conversations", q],
    queryFn: () => api.get<Page<Conversation>>("/ai/conversations", { q: q || undefined, page_size: 50 }),
  });
}

export function AssistantPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const list = useConversations(q);
  const status = useAiStatus();
  const chat = useChat(id ?? null, (newId) => navigate(`/assistant/${newId}`, { replace: true }));
  const [renaming, setRenaming] = useState<Conversation | null>(null);
  const [title, setTitle] = useState("");
  const [deleting, setDeleting] = useState<Conversation | null>(null);

  const refresh = () => qc.invalidateQueries({ queryKey: ["ai", "conversations"] });
  const rename = useMutation({
    mutationFn: () => api.patch(`/ai/conversations/${renaming!.id}`, { title }),
    onSuccess: () => { refresh(); setRenaming(null); toast.success("Conversation renamed"); },
    onError: (e) => toast.error(describeError(e)),
  });
  const remove = useMutation({
    mutationFn: (cid: string) => api.delete(`/ai/conversations/${cid}`),
    onSuccess: (_d, cid) => {
      refresh();
      setDeleting(null);
      toast.success("Conversation deleted");
      if (cid === id) navigate("/assistant");
    },
    onError: (e) => toast.error(describeError(e)),
  });

  return (
    <div className="rise grid min-h-0 flex-1 gap-4 md:grid-cols-[272px_minmax(0,1fr)]">
      <Card className="hidden min-h-0 flex-col overflow-hidden md:flex">
        <div className="flex flex-none items-center gap-2 p-3">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search chats" aria-label="Search conversations" className="h-9 pl-9" />
          </div>
          <IconButton label="New chat" onClick={() => { chat.reset(); navigate("/assistant"); }}>
            <MessageSquarePlus className="size-4" />
          </IconButton>
        </div>
        <div className="scroll-quiet min-h-0 flex-1 overflow-y-auto px-2 pb-2">
          {list.isLoading ? (
            <div className="space-y-2 p-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-11" />)}</div>
          ) : list.data?.items.length ? (
            groupByDay(list.data.items).map((g) => (
            <section key={g.label} className="mb-2">
            <h3 className="px-3 pt-2 pb-1 text-[11px] font-semibold tracking-wide text-ink-3 uppercase">{g.label}</h3>
            <ul className="space-y-0.5">
              {g.items.map((c) => (
                <li key={c.id} className="group relative">
                  <button
                    onClick={() => navigate(`/assistant/${c.id}`)}
                    className={cn("focus-ring w-full rounded-xl px-3 py-2 pr-9 text-left transition hover:bg-[var(--glass-2)]", c.id === id && "bg-[var(--glass-3)] shadow-[inset_2px_0_0_var(--ice)]")}
                  >
                    <span className="block truncate text-[13px] font-semibold">{c.title}</span>
                    <span className="block text-[11px] text-ink-3">{relative(c.last_message_at)}</span>
                  </button>
                  <div className="absolute top-1.5 right-1.5 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
                    <DropdownMenu trigger={<IconButton label={`Options for ${c.title}`} className="size-7"><MoreHorizontal className="size-4" /></IconButton>}>
                      <MenuItem icon={<Pencil className="size-4" />} onSelect={() => { setRenaming(c); setTitle(c.title); }}>Rename</MenuItem>
                      <MenuItem danger icon={<Trash2 className="size-4" />} onSelect={() => setDeleting(c)}>Delete</MenuItem>
                    </DropdownMenu>
                  </div>
                </li>
              ))}
            </ul>
            </section>
            ))
          ) : (
            <EmptyState title={q ? "No matching chats" : "No chats yet"} body={q ? undefined : "Your conversations are private to you."} />
          )}
        </div>
      </Card>

      <Card className="flex min-h-0 flex-col overflow-hidden">
        <div className="scroll-quiet min-h-0 flex-1 overflow-y-auto px-5 pt-6 pb-4 md:px-10">
          <div className="mx-auto h-full max-w-3xl">
            {chat.loading ? (
              <div className="space-y-4">{[0, 1].map((i) => <Skeleton key={i} className="h-16" />)}</div>
            ) : chat.items.length === 0 ? (
              <Welcome page={null} onPick={(t) => chat.send(t, null)} />
            ) : (
              <ErrorBoundary resetKey={chat.items.length} label="This conversation couldn't be shown.">
                <Messages items={chat.items} />
              </ErrorBoundary>
            )}
          </div>
        </div>
        {/* Docked composer; the thread fades out beneath it. */}
        <div className="relative flex-none px-4 pt-1 pb-3 md:px-10">
          <span aria-hidden className="pointer-events-none absolute inset-x-0 -top-8 h-8 bg-gradient-to-t from-[var(--glass-2)] to-transparent" />
          <div className="mx-auto flex max-w-3xl flex-col gap-2">
            <Composer
              autoFocus
              page={null}
              streaming={chat.streaming}
              disabled={status.data ? !status.data.configured : false}
              onSend={(t) => chat.send(t, null)}
              onStop={chat.stop}
            />
            <UsageLine />
          </div>
        </div>
      </Card>

      <Modal
        open={Boolean(renaming)}
        onOpenChange={(o) => !o && setRenaming(null)}
        title="Rename conversation"
        footer={<><Button variant="ghost" onClick={() => setRenaming(null)}>Cancel</Button><Button variant="primary" loading={rename.isPending} disabled={!title.trim()} onClick={() => rename.mutate()}>Save</Button></>}
      >
        <Input value={title} onChange={(e) => setTitle(e.target.value)} aria-label="Title" autoFocus />
      </Modal>
      <ConfirmDialog
        open={Boolean(deleting)}
        onOpenChange={(o) => !o && setDeleting(null)}
        title="Delete this conversation?"
        description="It will be removed from your history."
        confirmLabel="Delete conversation"
        loading={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
      />
    </div>
  );
}
