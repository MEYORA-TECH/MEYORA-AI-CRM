import {
  ArrowUp, Brain, Building2, CalendarClock, CalendarRange, CheckSquare, ChevronDown, ExternalLink, Globe, Handshake,
  Loader2, Magnet, Mail, Square, StickyNote, UserRound,
} from "@/components/icons";
import { useEffect, useRef, useState, type ReactNode } from "react";
import Markdown from "react-markdown";
import { Link } from "react-router-dom";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/format";
import { useCan } from "@/stores/auth";
import { ActionCard, ConfirmAllBar, type ActionUi } from "./actions";
import { Orb } from "./Orb";
import type { PageContext } from "./store";
import type { RecordsUi } from "./stream";
import { useAiStatus, type ChatItem } from "./useChat";

const TOOL_LABEL: Record<string, [string, string]> = {
  search_companies: ["Searching companies", "Searched companies"],
  get_company: ["Reading the company", "Read the company"],
  search_contacts: ["Searching contacts", "Searched contacts"],
  get_contact: ["Reading the contact", "Read the contact"],
  search_leads: ["Searching leads", "Searched leads"],
  get_lead: ["Reading the lead", "Read the lead"],
  search_deals: ["Searching deals", "Searched deals"],
  get_deal: ["Reading the deal", "Read the deal"],
  search_tasks: ["Checking tasks", "Checked tasks"],
  search_activities: ["Reading activity", "Read activity"],
  pipeline_summary: ["Totalling the pipeline", "Totalled the pipeline"],
  search_knowledge: ["Searching notes and call logs", "Searched notes and call logs"],
  remember: ["Saving to memory", "Saved to memory"],
  create_task: ["Preparing a task", "Prepared a task"],
  update_task: ["Preparing a task change", "Prepared a task change"],
  log_activity: ["Preparing an activity", "Prepared an activity"],
  add_note: ["Preparing a note", "Prepared a note"],
  create_lead: ["Preparing a lead", "Prepared a lead"],
  update_lead: ["Preparing a lead change", "Prepared a lead change"],
  update_deal: ["Preparing a deal change", "Prepared a deal change"],
  update_contact: ["Preparing a contact change", "Prepared a contact change"],
  draft_email: ["Drafting an email", "Drafted an email"],
  search_emails: ["Searching emails", "Searched emails"],
  get_email_thread: ["Reading the email thread", "Read the email thread"],
  web_search: ["Searching the web", "Searched the web"],
  research_company: ["Researching on the web", "Researched on the web"],
  research_lead: ["Researching on the web", "Researched on the web"],
  find_linkedin: ["Looking for their LinkedIn page", "Looked for their LinkedIn page"],
  draft_linkedin_message: ["Drafting a LinkedIn message", "Drafted a LinkedIn message"],
  save_linkedin_url: ["Preparing to save a LinkedIn page", "Prepared a LinkedIn page"],
};

const ENTITY: Record<RecordsUi["entity"], { icon: ReactNode; path?: string }> = {
  company: { icon: <Building2 className="size-3.5" />, path: "/companies" },
  contact: { icon: <UserRound className="size-3.5" />, path: "/contacts" },
  lead: { icon: <Magnet className="size-3.5" />, path: "/leads" },
  deal: { icon: <Handshake className="size-3.5" />, path: "/deals" },
  task: { icon: <CheckSquare className="size-3.5" />, path: "/tasks" },
  activity: { icon: <CalendarRange className="size-3.5" />, path: "/activities" },
  note: { icon: <StickyNote className="size-3.5" /> },
  email: { icon: <Mail className="size-3.5" /> },
};

/** The assistant's mark, kept under its old name for the places that import it. */
export function Spark({ className, thinking }: { className?: string; thinking?: boolean }) {
  return <Orb className={className} thinking={thinking} />;
}

/* ---------- Work trail: one quiet line per step, records on demand ---------- */

function TrailLine({ icon, label, detail, tag, open, onToggle, pending }: {
  icon: ReactNode; label: string; detail?: string; tag?: ReactNode; open?: boolean; onToggle?: () => void; pending?: boolean;
}) {
  const content = (
    <>
      <span className="grid size-5 place-items-center text-ink-3">{pending ? <Loader2 className="size-3.5 animate-spin" /> : icon}</span>
      <span className={cn("font-medium", pending ? "shimmer-text" : "text-ink-2")}>{label}</span>
      {detail ? <span className="num text-ink-3">· {detail}</span> : null}
      {tag}
      {onToggle ? <ChevronDown className={cn("size-3.5 text-ink-3 transition", open && "rotate-180")} /> : null}
    </>
  );
  return onToggle ? (
    <button type="button" onClick={onToggle} aria-expanded={open}
      className="focus-ring -mx-1.5 inline-flex max-w-full items-center gap-1.5 rounded-lg px-1.5 py-0.5 text-[12.5px] hover:bg-[var(--glass-2)]">
      {content}
    </button>
  ) : (
    <div className="inline-flex max-w-full items-center gap-1.5 py-0.5 text-[12.5px]">{content}</div>
  );
}

function ToolStep({ item }: { item: ChatItem }) {
  const [open, setOpen] = useState(false);
  const [label, done] = TOOL_LABEL[item.toolName ?? ""] ?? ["Looking up the CRM", "Looked up the CRM"];
  if (item.ui?.kind === "action") return <div className="py-1"><ActionCard ui={item.ui} /></div>;

  if (item.ui?.kind === "web") {
    const w = item.ui;
    return (
      <div>
        <TrailLine icon={<Globe className="size-3.5" />} label={done} detail={`${w.rows.length} source${w.rows.length === 1 ? "" : "s"}`}
          tag={<span className="rounded-full bg-tint-amber px-1.5 py-px text-[10px] font-semibold text-[#8a5200] dark:text-[#f2c47e]" title="From the public web, not your CRM. Check before relying on it.">web</span>}
          open={open} onToggle={w.rows.length ? () => setOpen(!open) : undefined} />
        {open ? (
          <ul className="glass-dense mt-1.5 mb-1 divide-y divide-[var(--line)] overflow-hidden rounded-2xl">
            {w.rows.map((r) => (
              <li key={r.ref}>
                <a href={r.url} target="_blank" rel="noreferrer noopener" className="focus-ring flex items-start gap-2.5 px-3 py-2 hover:bg-[var(--glass-2)]">
                  <span className="num mt-0.5 w-6 shrink-0 font-mono text-[10px] text-ink-3">{r.ref}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-semibold text-ink">{r.title}</span>
                    <span className="block truncate text-[11px] text-ink-3">{r.domain}{r.published ? ` · ${r.published.slice(0, 10)}` : ""} · {r.snippet}</span>
                  </span>
                  <ExternalLink className="mt-0.5 size-3 shrink-0 text-ink-3" />
                </a>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    );
  }

  if (item.ui?.kind === "memory") {
    const m = item.ui;
    return (
      <Link to="/memory" className="focus-ring inline-flex max-w-full items-start gap-2 rounded-xl bg-jade-soft px-2.5 py-1.5 text-[12.5px] text-ink-2 hover:brightness-105">
        <Brain className="mt-0.5 size-3.5 shrink-0 text-jade" />
        <span><span className="font-semibold text-ink">{m.action === "merged" ? "Already remembered" : "Remembered"}{m.scope === "user" ? " (just for you)" : ""}:</span> {m.content}</span>
      </Link>
    );
  }

  const ui = item.ui;
  const entity = ui ? ENTITY[ui.entity] : undefined;
  const linkable = ui && ui.entity !== "activity" && ui.entity !== "task";
  return (
    <div>
      <TrailLine
        pending={item.pending}
        icon={entity?.icon ?? <Building2 className="size-3.5" />}
        label={item.pending ? `${label}…` : done}
        detail={!item.pending && ui ? `${ui.total} found` : undefined}
        open={open}
        onToggle={!item.pending && ui?.rows.length ? () => setOpen(!open) : undefined}
      />
      {open && ui ? (
        <ul className="glass-dense mt-1.5 mb-1 divide-y divide-[var(--line)] overflow-hidden rounded-2xl">
          {ui.rows.map((r) => {
            const body = (
              <>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-semibold text-ink">{r.title}</span>
                  {r.subtitle ? <span className="block truncate text-[11px] text-ink-3">{r.subtitle}</span> : null}
                </span>
                {r.value ? <span className="num text-[12px] font-semibold text-ink">{r.value}</span> : null}
                {r.badge ? <span className="rounded-full bg-tint-slate px-2 py-0.5 text-[10px] font-semibold text-ink-2">{r.badge.replace(/_/g, " ")}</span> : null}
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
    <div className="mb-2">
      <TrailLine icon={<Brain className="size-3.5" />} label={`Used ${items.length} memor${items.length === 1 ? "y" : "ies"}`}
        open={open} onToggle={() => setOpen(!open)} />
      {open ? (
        <ul className="glass-dense mt-1.5 divide-y divide-[var(--line)] rounded-2xl text-xs">
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

function withCitations(text: string, sources: Map<string, string>) {
  // Some models write 【w1】 instead of [w1]; accept both.
  return text.replace(/[[【](w\d+)[\]】]/g, (m, ref) => (sources.has(ref) ? `[[${ref}]](${sources.get(ref)})` : m));
}

function AssistantText({ item, sources }: { item: ChatItem; sources: Map<string, string> }) {
  if (item.error) {
    return <p role="alert" className="rounded-2xl bg-danger-soft px-3.5 py-2.5 text-sm font-medium text-danger">{item.error}</p>;
  }
  if (item.pending && !item.content) {
    return (
      <div className="py-1">
        <p className="shimmer-text text-[14.5px] font-medium">Thinking</p>
        {item.status ? (
          <p className="mt-1 flex items-center gap-1.5 text-xs text-ink-3"><CalendarClock className="size-3.5" /> {item.status}</p>
        ) : null}
      </div>
    );
  }
  return (
    <div className="prose-chat text-[14.5px] leading-[1.7] text-ink">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Only follow in-app or http(s) links the model wrote; never javascript: etc.
          a: ({ href, children }) =>
            href?.startsWith("/") ? <Link to={href} className="font-semibold text-jade underline-offset-2 hover:underline">{children}</Link>
            : /^https?:\/\//.test(href ?? "") ? <a href={href} target="_blank" rel="noreferrer noopener" className="font-semibold text-jade underline-offset-2 hover:underline">{children}</a>
            : <span>{children}</span>,
        }}
      >
        {withCitations(item.content, sources)}
      </Markdown>
      {item.pending ? <span className="ml-0.5 inline-block h-4 w-[3px] animate-pulse rounded-full bg-ice align-middle" /> : null}
    </div>
  );
}

/** Action proposals made in the turn that ends with this assistant message. */
function turnActions(items: ChatItem[], assistantKey: string): ActionUi[] {
  const at = items.findIndex((i) => i.key === assistantKey);
  const out: ActionUi[] = [];
  for (let i = at - 1; i >= 0 && items[i].role === "tool"; i--) {
    const ui = items[i].ui;
    if (ui?.kind === "action") out.unshift(ui);
  }
  return out;
}

export function Messages({ items, compact }: { items: ChatItem[]; compact?: boolean }) {
  const end = useRef<HTMLDivElement>(null);
  const sources = new Map<string, string>();
  for (const i of items) if (i.ui?.kind === "web") for (const r of i.ui.rows) sources.set(r.ref, r.url);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [items]);
  const avatar = compact ? "size-6" : "size-7";
  return (
    <div className={cn("flex flex-col", compact ? "gap-4" : "gap-6")} aria-live="polite">
      {items.map((item, index) => {
        if (item.role === "user") {
          return (
            <div key={item.key} className="ml-auto max-w-[82%] rounded-[20px] rounded-br-[6px] border border-[var(--line)] bg-jade-soft px-4 py-2.5 text-[14.5px] leading-relaxed whitespace-pre-wrap text-ink">
              {item.content}
            </div>
          );
        }
        if (item.role === "tool") {
          // Steps hang off a hairline under the orb, so a turn reads as one piece of work.
          const first = items[index - 1]?.role !== "tool";
          return (
            <div key={item.key} className={cn("relative", compact ? "pl-9" : "pl-10", !first && (compact ? "-mt-3" : "-mt-5"))}>
              <span aria-hidden className={cn("absolute top-0 bottom-0 w-px bg-[var(--line-strong)]", compact ? "left-3" : "left-3.5")} />
              <ToolStep item={item} />
            </div>
          );
        }
        const afterTools = items[index - 1]?.role === "tool";
        return (
          <div key={item.key} className={cn("flex gap-3", afterTools && (compact ? "-mt-2" : "-mt-3"))}>
            <Orb className={cn(avatar, "mt-0.5")} thinking={item.pending && !item.content} />
            <div className="min-w-0 max-w-[68ch] flex-1">
              {item.memories?.length ? <UsedMemories items={item.memories} /> : null}
              <AssistantText item={item} sources={sources} />
              <div className="mt-2"><ConfirmAllBar actions={turnActions(items, item.key)} /></div>
            </div>
          </div>
        );
      })}
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
    el.style.height = `${Math.min(el.scrollHeight, 168)}px`;
  }, [text]);

  const submit = () => {
    if (!text.trim() || disabled || streaming) return;
    onSend(text);
    setText("");
  };

  return (
    <div className="glass-dense rounded-[22px] p-2 shadow-[0_10px_30px_-14px_rgb(24_44_60/0.35)] transition-[border-color,box-shadow] focus-within:border-[rgb(94_140_168/0.55)] focus-within:shadow-[0_0_0_4px_rgb(94_140_168/0.14),0_10px_30px_-14px_rgb(24_44_60/0.35)]">
      {page ? (
        <div className="px-1.5 pt-0.5 pb-1">
          <span className="inline-flex max-w-full items-center gap-1.5 rounded-full bg-jade-soft px-2.5 py-0.5 text-[11px] font-semibold text-jade">
            <span className="size-1.5 rounded-full bg-ice" /> <span className="truncate">Looking at {page.name}</span>
          </span>
        </div>
      ) : null}
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
        aria-label="Ask Nila"
        placeholder={disabled ? "The assistant isn't set up yet" : page ? `Ask about ${page.name}…` : "Ask about your deals, leads and customers…"}
        className="block max-h-42 min-h-10 w-full resize-none border-0 bg-transparent px-2.5 py-2 text-[15px] leading-relaxed shadow-none ring-0 outline-none placeholder:text-ink-3 focus:ring-0 focus:outline-none focus-visible:outline-none"
      />
      <div className="flex items-center justify-between gap-2 pl-2.5">
        <span className="hidden text-[11px] text-ink-3 sm:inline">
          <kbd className="font-sans font-semibold">Enter</kbd> to send · <kbd className="font-sans font-semibold">Shift + Enter</kbd> for a new line
        </span>
        {streaming ? (
          <button type="button" onClick={onStop} aria-label="Stop answering"
            className="focus-ring ml-auto flex size-9 items-center justify-center rounded-full bg-[var(--ink)] text-[var(--canvas)] transition hover:opacity-90">
            <Square className="size-3.5" weight="fill" />
          </button>
        ) : (
          <button type="button" onClick={submit} disabled={!text.trim() || disabled} aria-label="Send"
            className="focus-ring ml-auto flex size-9 items-center justify-center rounded-full bg-[var(--ink)] text-[var(--canvas)] transition hover:opacity-90 disabled:opacity-25">
            <ArrowUp className="size-4" weight="bold" />
          </button>
        )}
      </div>
    </div>
  );
}

/* ---------- Welcome: what to ask, and whether it's set up ---------- */

const GENERAL: { text: string; icon: ReactNode }[] = [
  { text: "What should I focus on today?", icon: <CheckSquare className="size-4" /> },
  { text: "Which open deals have had no activity in 14 days?", icon: <Handshake className="size-4" /> },
  { text: "Which leads haven't been contacted in a week?", icon: <Magnet className="size-4" /> },
  { text: "Summarise the pipeline by stage", icon: <CalendarRange className="size-4" /> },
];

const FOR_PAGE: Record<PageContext["type"], string[]> = {
  company: ["Summarise this company", "What open deals do we have with them?", "What happened here recently?"],
  contact: ["What have we discussed with them?", "When did we last contact them?", "What deals are they part of?"],
  lead: ["Summarise this lead", "Has anyone contacted this lead?", "How does this lead compare to our other leads?"],
  deal: ["Summarise this deal", "Why might this deal be stuck?", "What happened on this deal recently?"],
};

export function Welcome({ page, onPick, compact }: { page: PageContext | null; onPick: (t: string) => void; compact?: boolean }) {
  const status = useAiStatus();
  const isOwner = useCan("org:secrets");
  const suggestions = page ? FOR_PAGE[page.type].map((text) => ({ text, icon: ENTITY[page.type].icon })) : GENERAL;
  return (
    <div className={cn("flex flex-col", compact ? "items-start gap-4 py-1" : "min-h-full items-center justify-center gap-6 py-2 text-center [@media(max-height:820px)]:gap-4")}>
      <Orb className={compact ? "size-11" : "size-16 [@media(max-height:820px)]:size-12"} />
      <div className={cn(!compact && "max-w-md")}>
        <h2 className={cn("font-display font-bold tracking-[-0.02em]", compact ? "text-lg" : "text-[26px] leading-tight [@media(max-height:820px)]:text-[22px]")}>
          {page ? `Ask about ${page.name}` : "What can I help you with?"}
        </h2>
        <p className="mt-1.5 text-sm text-ink-2">
          Nila reads your CRM, remembers what matters, and prepares changes for you to approve. Every answer links to the records it used.
        </p>
      </div>
      {status.data && !status.data.configured ? (
        <p className="rounded-2xl bg-tint-amber px-3.5 py-2.5 text-left text-sm">
          The assistant needs an AI key before it can answer.{" "}
          {isOwner ? (
            <Link to="/settings?tab=api-keys" className="font-semibold underline underline-offset-2">Add a Groq key in Settings → API keys</Link>
          ) : (
            "Ask your workspace owner to add one in Settings → API keys."
          )}
        </p>
      ) : (
        <div className={cn("grid w-full gap-2", compact ? "" : "max-w-xl sm:grid-cols-2")}>
          {suggestions.map((s) => (
            <button
              key={s.text}
              onClick={() => onPick(s.text)}
              className="focus-ring glass-soft group flex items-start gap-2.5 rounded-2xl px-3.5 py-3 text-left [@media(max-height:820px)]:py-2.5 text-[13.5px] font-medium text-ink-2 transition hover:-translate-y-px hover:text-ink"
            >
              <span className="mt-px text-ink-3 transition group-hover:text-jade">{s.icon}</span>
              {s.text}
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
    <div className="flex items-center justify-center gap-2 text-[11px] text-ink-3" title="AI used today out of your daily allowance">
      <span className="h-1 w-14 overflow-hidden rounded-full bg-[var(--line-strong)]">
        <span className={cn("block h-full rounded-full", pct > 85 ? "bg-danger" : "bg-ice")} style={{ width: `${pct}%` }} />
      </span>
      <span className="num">{Math.round(pct)}% of today's AI allowance</span>
    </div>
  );
}
