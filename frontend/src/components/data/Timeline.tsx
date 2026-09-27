import { Link } from "react-router-dom";
import { ArrowRightLeft, CalendarClock, CheckSquare, Mail, MessageSquareText, Phone, Sparkles, StickyNote, Users } from "@/components/icons";
import type { ReactNode } from "react";

import { EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { useMembers, useTimeline } from "@/hooks/resources";
import { cn, dateTime, label, relative } from "@/lib/format";
import { describeError } from "@/services/api";
import type { TimelineItem } from "@/types";

const ICONS: Record<string, ReactNode> = {
  call: <Phone className="size-3.5" />,
  meeting: <Users className="size-3.5" />,
  email: <Mail className="size-3.5" />,
  note: <StickyNote className="size-3.5" />,
  follow_up: <CalendarClock className="size-3.5" />,
  stage_change: <ArrowRightLeft className="size-3.5" />,
  system: <Sparkles className="size-3.5" />,
  task: <CheckSquare className="size-3.5" />,
};

function iconFor(item: TimelineItem) {
  if (item.kind === "email") return ICONS.email;
  if (item.kind === "note") return ICONS.note;
  if (item.kind === "task") return ICONS.task;
  return ICONS[item.type ?? ""] ?? <MessageSquareText className="size-3.5" />;
}

function caption(item: TimelineItem) {
  if (item.kind === "email") return item.type === "sent" ? "Email sent" : "Email received";
  if (item.kind === "task") return `Task · ${label(item.status)}`;
  if (item.kind === "note") return "Note";
  return item.status === "planned" ? `${label(item.type)} · planned` : label(item.type);
}

/** Unified history for one record: activities, tasks and notes, newest first. */
export function Timeline({ entity, id }: { entity: "companies" | "contacts" | "leads" | "deals"; id: string }) {
  const { data, isLoading, error, refetch } = useTimeline(entity, id);
  const members = useMembers();
  const who = (actorId: string | null) => members.data?.find((m) => m.user.id === actorId)?.user.full_name;

  if (isLoading) {
    return (
      <div className="space-y-4 p-5">
        {[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}
      </div>
    );
  }
  if (error) return <ErrorState message={describeError(error)} onRetry={() => refetch()} />;
  if (!data?.length) {
    return (
      <EmptyState
        icon={<CalendarClock className="size-5" />}
        title="Nothing logged yet"
        body="Calls, meetings, notes, tasks and stage changes for this record will appear here."
      />
    );
  }

  return (
    <ol className="relative px-5 py-4">
      <span aria-hidden className="absolute top-6 bottom-6 left-[33px] w-px bg-[var(--line-strong)]" />
      {data.map((item) => (
        <li key={`${item.kind}-${item.id}`} className="relative flex gap-4 py-2.5">
          <span
            className={cn(
              "relative z-10 mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border border-[var(--glass-edge)]",
              item.type === "stage_change" ? "bg-tint-violet" : item.kind === "email" ? "bg-tint-sky" : item.kind === "note" ? "bg-tint-amber" : item.kind === "task" ? "bg-tint-sky" : "bg-jade-soft text-jade",
            )}
          >
            {iconFor(item)}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3">
              {item.kind === "email" ? (
                <Link to={`/emails/${item.id}`} className="text-sm font-semibold text-ink hover:text-jade hover:underline">{item.title}</Link>
              ) : (
                <p className="text-sm font-semibold text-ink">{item.title}</p>
              )}
              <time className="font-mono text-[11px] text-ink-3" dateTime={item.at} title={dateTime(item.at)}>
                {relative(item.at)}
              </time>
            </div>
            <p className="text-xs text-ink-3">
              {caption(item)}
              {who(item.actor_id) ? ` · ${who(item.actor_id)}` : ""}
            </p>
            {item.body ? <p className="mt-1.5 text-sm whitespace-pre-line text-ink-2">{item.body}</p> : null}
          </div>
        </li>
      ))}
    </ol>
  );
}
