import { ArrowDownLeft, ArrowUpRight, Mail, Paperclip, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

import { useAiUi } from "@/ai/store";
import { Badge, Button, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { cn, dateTime, relative } from "@/lib/format";
import { describeError } from "@/services/api";
import { useAuth } from "@/stores/auth";
import { participantsLabel, people, useThread, useThreads, type EmailThread, type Participant } from "./api";

export function ThreadList({ threads, activeId, compact }: { threads: EmailThread[]; activeId?: string; compact?: boolean }) {
  const me = useAuth((s) => s.me);
  return (
    <ul className="divide-y divide-[var(--line)]">
      {threads.map((t) => (
        <li key={t.id}>
          <Link
            to={`/emails/${t.id}`}
            className={cn("focus-ring block px-5 py-3 transition hover:bg-[var(--glass-2)]", t.id === activeId && "bg-[var(--glass-3)]")}
          >
            <div className="flex items-baseline justify-between gap-3">
              <p className="truncate text-sm font-semibold">{participantsLabel(t, me?.email)}</p>
              <time className="shrink-0 font-mono text-[11px] text-ink-3" dateTime={t.last_message_at}>{relative(t.last_message_at)}</time>
            </div>
            <p className="truncate text-[13px] text-ink">
              {t.subject}
              {t.message_count > 1 ? <span className="num ml-1.5 text-ink-3">({t.message_count})</span> : null}
            </p>
            {!compact ? <p className="truncate text-xs text-ink-3">{t.snippet}</p> : null}
          </Link>
        </li>
      ))}
    </ul>
  );
}

/** "Emails" tab on a company or contact. */
export function RecordEmailsPanel({ field, id }: { field: "company_id" | "contact_id"; id: string }) {
  const list = useThreads({ [field]: id });
  if (list.isLoading) return <div className="space-y-3 p-5">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div>;
  if (list.error) return <ErrorState message={describeError(list.error)} onRetry={() => list.refetch()} />;
  if (!list.data?.items.length) {
    return (
      <EmptyState icon={<Mail className="size-5" />} title="No emails yet"
        body="Emails with this record appear here once a teammate connects Gmail in Settings." />
    );
  }
  return <ThreadList threads={list.data.items} />;
}

export function ThreadView({ id }: { id: string }) {
  const thread = useThread(id);
  const ask = useAiUi((s) => s.ask);
  if (thread.isLoading) return <div className="space-y-4 p-6"><Skeleton className="h-8 w-2/3" /><Skeleton className="h-40" /></div>;
  if (thread.error || !thread.data) return <ErrorState message={describeError(thread.error)} onRetry={() => thread.refetch()} />;
  const t = thread.data;
  const who = people(t).filter((p) => !t.messages.some((m) => m.direction === "outbound" && m.from_email === p.email));
  const about = `the email thread "${t.subject}"${who[0] ? ` with ${who[0].name || who[0].email}` : ""}`;

  return (
    <div className="flex min-h-0 flex-col">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-6 py-4">
        <div className="min-w-0">
          <h2 className="text-lg font-bold tracking-tight">{t.subject}</h2>
          <p className="text-xs text-ink-3">{t.message_count} message{t.message_count === 1 ? "" : "s"} · last {dateTime(t.last_message_at)}</p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" icon={<Sparkles className="size-4" />} onClick={() => ask(`Summarise ${about}: what was asked, promised and still open?`)}>Summarise</Button>
          <Button size="sm" icon={<Sparkles className="size-4" />} onClick={() => ask(`Draft a reply to ${about}. Keep it short and specific to what they asked.`)}>Draft reply</Button>
        </div>
      </div>
      <ol className="flex flex-col gap-3 p-5">
        {t.messages.map((m) => (
          <li key={m.id} className={cn("glass-dense rounded-2xl p-4", m.direction === "outbound" && "ml-8 bg-[var(--jade-soft)]")}>
            <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
              {m.direction === "outbound" ? <ArrowUpRight className="size-3.5 text-jade" /> : <ArrowDownLeft className="size-3.5 text-ink-3" />}
              <span className="font-semibold text-ink">{m.direction === "outbound" ? "You" : m.from_name || m.from_email}</span>
              {m.direction === "inbound" && m.from_name ? <span className="text-ink-3">{m.from_email}</span> : null}
              <span className="text-ink-3">to {(m.to as unknown as Participant[]).map((a) => a.name || a.email).join(", ")}</span>
              {m.has_attachments ? <Badge className="h-5 px-2 text-[10px]"><Paperclip className="size-3" /> Attachment</Badge> : null}
              <time className="ml-auto font-mono text-[11px] text-ink-3">{dateTime(m.sent_at)}</time>
            </div>
            <p className="text-sm leading-relaxed whitespace-pre-wrap text-ink">{m.body_text || "(no text)"}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}
