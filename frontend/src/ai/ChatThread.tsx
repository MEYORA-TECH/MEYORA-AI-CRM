import { ArrowUp, Brain, Building2, CheckSquare, ChevronDown, Handshake, Loader2, Magnet, Square, StickyNote, UserRound, CalendarRange, Sparkles } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import Markdown from "react-markdown";
import { Link } from "react-router-dom";
import remarkGfm from "remark-gfm";

import { Badge } from "@/components/ui/primitives";
import { cn } from "@/lib/format";
import type { PageContext } from "./store";
import type { RecordsUi } from "./stream";
import { useAiStatus, type ChatItem } from "./useChat";

const TOOL_LABEL: Record<string, [string, string]> = {
  search_companies: ["Searching companies", "Searched companies"],
  get_company: ["Reading company", "Read company"],
  search_contacts: ["Searching contacts", "Searched contacts"],
  get_contact: ["Reading contact", "Read contact"],
  search_leads: ["Searching leads", "Searched leads"],
  get_lead: ["Reading lead", "Read lead"],
  search_deals: ["Searching deals", "Searched deals"],
  get_deal: ["Reading deal", "Read deal"],
  search_tasks: ["Checking tasks", "Checked tasks"],
  search_activities: ["Reading activity", "Read activity"],
  pipeline_summary: ["Totalling the pipeline", "Totalled the pipeline"],
  search_knowledge: ["Searching notes and call logs", "Searched notes and call logs"],
  remember: ["Saving to memory", "Saved to memory"],
};

const ENTITY: Record<RecordsUi["entity"], { icon: ReactNode; path?: string }> = {
  company: { icon: <Building2 className="size-3.5" />, path: "/companies" },
  contact: { icon: <UserRound className="size-3.5" />, path: "/contacts" },
  lead: { icon: <Magnet className="size-3.5" />, path: "/leads" },
  deal: { icon: <Handshake className="size-3.5" />, path: "/deals" },
  task: { icon: <CheckSquare className="size-3.5" />, path: "/tasks" },
  activity: { icon: <CalendarRange className="size-3.5" />, path: "/activities" },
  note: { icon: <StickyNote className="size-3.5" /> },
};

export function Spark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center justify-center rounded-full bg-[conic-gradient(from_210deg,var(--jade),#8a7cf0,#e9a36b,var(--jade))] text-white", className)}>
      <Sparkles className="size-[60%]" strokeWidth={2.4} />
    </span>
  );
}

/* ---------- Tool step: the records the answer is based on ---------- */

function ToolStep({ item, compact }: { item: ChatItem; compact?: boolean }) {
  const [label, done] = TOOL_LABEL[item.toolName ?? ""] ?? ["Looking up the CRM", "Looked up the CRM"];
  if (item.ui?.kind === "memory") {
    const m = item.ui;
    return (
      <Link to="/memory" className="focus-ring glass-dense flex items-start gap-2.5 rounded-xl px-3 py-2.5 text-xs hover:bg-[var(--glass-2)]">
        <Brain className="mt-0.5 size-4 shrink-0 text-jade" />
        <span>
          <span className="block font-semibold text-ink">
            {m.action === "merged" ? "Already remembered" : "Remembered"}
            {m.scope === "user" ? " (just for you)" : ""}
          </span>
          <span className="block text-ink-2">{m.content}</span>
        </span>
      </Link>
    );
  }
  const ui = item.ui;
  const entity = ui ? ENTITY[ui.entity] : undefined;
  const linkable = ui && ui.entity !== "activity" && ui.entity !== "task";
  return (
    <div className="text-xs">
      <div className="flex items-center gap-2 text-ink-3">
        {item.pending ? <Loader2 className="size-3.5 animate-spin" /> : entity?.icon}
        <span className="font-semibold">{item.pending ? `${label}…` : done}</span>
        {!item.pending && ui ? <span className="num">· {ui.total} found</span> : null}
        {!item.pending ? <Badge tint="jade" className="h-5 px-2 text-[10px]">CRM</Badge> : null}
      </div>
      {ui && ui.rows.length ? (
        <ul className={cn("glass-dense mt-1.5 divide-y divide-[var(--line)] overflow-hidden rounded-xl", compact && "max-h-56 overflow-y-auto")}>
          {ui.rows.map((r) => {
            const body = (
              <>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-semibold text-ink">{r.title}</span>
                  {r.subtitle ? <span className="block truncate text-[11px] text-ink-3">{r.subtitle}</span> : null}
                </span>
                {r.value ? <span className="num text-[12px] font-semibold text-ink">{r.value}</span> : null}
                {r.badge ? <Badge className="h-5 px-2 text-[10px]">{r.badge.replace(/_/g, " ")}</Badge> : null}
              </>
            );
            const href = r.href ?? (linkable && entity?.path ? `${entity.path}/${r.id}` : null);
            return (
              <li key={r.id}>
                {href ? (
                  <Link to={href} className="focus-ring flex items-center gap-2.5 px-3 py-2 hover:bg-[var(--glass-2)]">{body}</Link>
                ) : (
                  <div className="flex items-center gap-2.5 px-3 py-2">{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

/* ---------- Messages ---------- */

function UsedMemories({ items }: { items: NonNullable<ChatItem["memories"]> }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mb-2 text-xs">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="focus-ring inline-flex items-center gap-1.5 rounded-full bg-jade-soft px-2.5 py-1 font-semibold text-jade"
      >
        <Brain className="size-3.5" /> Used {items.length} memor{items.length === 1 ? "y" : "ies"}
        <ChevronDown className={cn("size-3.5 transition", open && "rotate-180")} />
      </button>
      {open ? (
        <ul className="glass-dense mt-1.5 divide-y divide-[var(--line)] rounded-xl">
          {items.map((m) => (
            <li key={m.id} className="px-3 py-2 text-ink-2">
              {m.content} <span className="text-ink-3">· {m.scope === "user" ? "just for you" : `from ${m.source_type}`}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function AssistantText({ item }: { item: ChatItem }) {
  if (item.error) {
    return <p role="alert" className="rounded-xl bg-danger-soft px-3 py-2 text-sm font-medium text-danger">{item.error}</p>;
  }
  if (item.pending && !item.content) {
    return <p className="flex items-center gap-2 text-sm text-ink-3"><Loader2 className="size-4 animate-spin" /> Thinking…</p>;
  }
  return (
    <div className="prose-chat text-sm leading-relaxed text-ink">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Only follow in-app or http(s) links the model wrote; never javascript: etc.
          a: ({ href, children }) =>
            href?.startsWith("/") ? <Link to={href} className="font-semibold text-jade hover:underline">{children}</Link>
            : /^https?:\/\//.test(href ?? "") ? <a href={href} target="_blank" rel="noreferrer noopener" className="font-semibold text-jade hover:underline">{children}</a>
            : <span>{children}</span>,
        }}
      >
        {item.content}
      </Markdown>
      {item.pending ? <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-jade align-middle" /> : null}
    </div>
  );
}

export function Messages({ items, compact }: { items: ChatItem[]; compact?: boolean }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ block: "end" }), [items]);
  return (
    <div className="flex flex-col gap-4" aria-live="polite">
      {items.map((item) =>
        item.role === "user" ? (
          <div key={item.key} className="ml-auto max-w-[85%] rounded-[18px] rounded-br-md bg-[var(--ink)] px-3.5 py-2.5 text-sm whitespace-pre-wrap text-[var(--canvas)]">
            {item.content}
          </div>
        ) : item.role === "tool" ? (
          <div key={item.key} className="pl-9"><ToolStep item={item} compact={compact} /></div>
        ) : (
          <div key={item.key} className="flex gap-2.5">
            <Spark className="mt-0.5 size-6 shrink-0" />
            <div className="min-w-0 flex-1">
              {item.memories?.length ? <UsedMemories items={item.memories} /> : null}
              <AssistantText item={item} />
            </div>
          </div>
        ),
      )}
      <div ref={end} />
    </div>
  );
}

/* ---------- Composer ---------- */

export function Composer({ onSend, onStop, streaming, disabled, page, autoFocus }: {
  onSend: (text: string) => void;
  onStop: () => void;
  streaming: boolean;
  disabled?: boolean;
  page: PageContext | null;
  autoFocus?: boolean;
}) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [text]);

  const submit = () => {
    if (!text.trim() || disabled || streaming) return;
    onSend(text);
    setText("");
  };

  return (
    <div className="glass-dense rounded-[20px] p-2">
      {page ? (
        <p className="px-2 pt-1 pb-1.5 text-[11px] font-semibold text-ink-3">
          Looking at <span className="text-ink-2">{page.name}</span>
        </p>
      ) : null}
      <div className="flex items-end gap-2">
        <textarea
          ref={ref}
          rows={1}
          autoFocus={autoFocus}
          value={text}
          disabled={disabled}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          aria-label="Ask Meyora"
          placeholder={disabled ? "The assistant isn't set up yet" : "Ask about your deals, leads, customers…"}
          className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-ink-3"
        />
        {streaming ? (
          <button type="button" onClick={onStop} aria-label="Stop" className="focus-ring flex size-9 items-center justify-center rounded-full bg-[var(--ink)] text-[var(--canvas)]">
            <Square className="size-3.5" fill="currentColor" />
          </button>
        ) : (
          <button type="button" onClick={submit} disabled={!text.trim() || disabled} aria-label="Send"
            className="focus-ring flex size-9 items-center justify-center rounded-full bg-jade text-jade-ink transition disabled:opacity-40">
            <ArrowUp className="size-4" strokeWidth={2.5} />
          </button>
        )}
      </div>
    </div>
  );
}

/* ---------- Empty state with suggestions ---------- */

const GENERAL = [
  "What should I focus on today?",
  "Which open deals have had no activity in 14 days?",
  "Which leads haven't been contacted in a week?",
  "Summarise the pipeline by stage",
];

const FOR_PAGE: Record<PageContext["type"], string[]> = {
  company: ["Summarise this company", "What open deals do we have with them?", "What happened here recently?"],
  contact: ["What have we discussed with them?", "When did we last contact them?", "What deals are they part of?"],
  lead: ["Summarise this lead", "Has anyone contacted this lead?", "How does this lead compare to our other leads?"],
  deal: ["Summarise this deal", "Why might this deal be stuck?", "What happened on this deal recently?"],
};

export function Welcome({ page, onPick }: { page: PageContext | null; onPick: (t: string) => void }) {
  const status = useAiStatus();
  const suggestions = page ? FOR_PAGE[page.type] : GENERAL;
  return (
    <div className="flex flex-col items-start gap-4 py-2">
      <Spark className="size-10" />
      <div>
        <p className="text-lg font-extrabold tracking-tight">Ask Meyora</p>
        <p className="mt-0.5 text-sm text-ink-2">
          Answers come from your CRM records, and every result links back to them. Meyora can read the CRM; making changes comes later.
        </p>
      </div>
      {status.data && !status.data.configured ? (
        <p className="rounded-xl bg-tint-amber px-3 py-2 text-sm">
          The assistant isn't set up yet. Add a <span className="font-mono text-[12px]">GROQ_API_KEY</span> to the server's environment to turn it on.
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button key={s} onClick={() => onPick(s)} className="focus-ring glass-soft rounded-full px-3.5 py-2 text-left text-[13px] font-medium text-ink-2 transition hover:text-ink">
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function UsageLine() {
  const status = useAiStatus();
  if (!status.data?.configured) return null;
  const pct = Math.min(100, (status.data.used_today / status.data.quota) * 100);
  return (
    <div className="flex items-center gap-2 text-[11px] text-ink-3" title="Tokens used today out of your daily allowance">
      <span className="h-1 w-16 overflow-hidden rounded-full bg-[var(--line-strong)]">
        <span className={cn("block h-full rounded-full", pct > 85 ? "bg-danger" : "bg-jade")} style={{ width: `${pct}%` }} />
      </span>
      <span className="num">{Math.round(pct)}% of today's AI allowance</span>
    </div>
  );
}
