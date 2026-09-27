import { useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Orb } from "@/ai/Orb";
import { useAiUi } from "@/ai/store";
import { LogActivityButton } from "@/components/data/Related";
import {
  AlertTriangle, ArrowUpRight, Building2, CalendarClock, CheckSquare, Handshake, Magnet, Mail, Phone, Plus, UsersRound,
} from "@/components/icons";
import { Scroller } from "@/components/ui/Scroller";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorState, Skeleton, tintBg } from "@/components/ui/primitives";
import { tasks as taskRes, useDashboard } from "@/hooks/resources";
import { cn, dateTime, label, money, relative, timeZone } from "@/lib/format";
import { TASK_PRIORITY } from "@/lib/status";
import { describeError } from "@/services/api";
import { useAuth, useCan } from "@/stores/auth";
import type { Dashboard } from "@/types";

type Insights = Dashboard["insights"];

/** Dashboard panels fill their grid cell on large screens; lists show what fits and fade out. */
const PANEL = "flex flex-col overflow-hidden lg:min-h-0";
const pct = (part: number, whole: number) => (whole ? Math.round((part / whole) * 100) : 0);
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

/* ---------------- Headline figures ---------------- */

function Kpi({ icon, tint, label: title, value, sub, to, meter }: {
  icon: ReactNode; tint: string; label: string; value: string; sub: string; to: string; meter?: number;
}) {
  return (
    <Link to={to} className="focus-ring glass group relative flex min-w-0 flex-col rounded-[20px] p-3.5 transition hover:-translate-y-0.5 [@media(max-height:760px)]:p-3">
      <div className="flex items-center gap-2">
        <span className={cn("grid size-7 shrink-0 place-items-center rounded-lg", tintBg(tint))}>{icon}</span>
        <span className="truncate text-[12.5px] font-semibold text-ink-2">{title}</span>
        <ArrowUpRight className="ml-auto size-3.5 shrink-0 text-ink-3 opacity-0 transition group-hover:opacity-100" />
      </div>
      <p className="num mt-2 truncate font-display text-[24px] leading-none font-bold tracking-[-0.03em] text-ink [@media(max-height:760px)]:text-[21px]">
        {value}
      </p>
      <p className="mt-1.5 truncate text-[11.5px] text-ink-3">{sub}</p>
      {meter !== undefined ? (
        <span className="mt-2 h-1 overflow-hidden rounded-full bg-[var(--line)]">
          <span className="block h-full rounded-full bg-ice" style={{ width: `${Math.min(100, meter)}%` }} />
        </span>
      ) : null}
    </Link>
  );
}

function Headline({ d }: { d: Dashboard }) {
  const i = d.insights;
  const c = i.coverage;
  return (
    <div className="rise grid flex-none grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6" style={{ animationDelay: "40ms" }}>
      <Kpi to="/leads" tint="sky" icon={<Magnet className="size-4" />} label="Leads to contact" value={String(i.to_contact)}
        sub={`${i.fit.top} with fit 90+ · none in ${i.stale_days} days`} />
      <Kpi to="/companies" tint="violet" icon={<Building2 className="size-4" />} label="Prospect companies" value={String(c.companies)}
        sub={c.partners ? `+ ${plural(c.partners, "outreach partner")}` : "In your CRM"} />
      <Kpi to="/contacts" tint="emerald" icon={<UsersRound className="size-4" />} label="Decision makers found"
        value={`${pct(c.with_decision_maker, c.companies)}%`} meter={pct(c.with_decision_maker, c.companies)}
        sub={`${c.companies - c.with_contacts} companies have no contact yet`} />
      <Kpi to="/deals" tint="amber" icon={<Handshake className="size-4" />} label="Open pipeline"
        value={money(d.pipeline.pipeline_value, d.currency, { compact: true })}
        sub={`${plural(d.pipeline.open_deals, "deal")} · ${money(d.pipeline.weighted_value, d.currency, { compact: true })} weighted`} />
      <Kpi to="/deals?view=list&status=won" tint="emerald" icon={<CheckSquare className="size-4" />} label="Won this month"
        value={money(d.pipeline.revenue_this_month, d.currency, { compact: true })}
        sub={`${d.pipeline.won_deals} won · ${d.pipeline.lost_deals} lost all time`} />
      <Kpi to="/tasks" tint={d.tasks.overdue ? "rose" : "slate"} icon={<CalendarClock className="size-4" />} label="My tasks"
        value={String(d.tasks.due_today + d.tasks.overdue)}
        sub={d.tasks.overdue ? `${d.tasks.due_today} due today · ${d.tasks.overdue} overdue` : `due today · ${d.tasks.open} open`} />
    </div>
  );
}

/* ---------------- Contact next: the most useful list on the page ---------------- */

function FitScore({ score }: { score: number }) {
  const tone = score >= 90 ? "var(--jade)" : score >= 80 ? "var(--ice)" : score >= 70 ? "var(--frost)" : "var(--line-strong)";
  return (
    <span className="relative grid size-9 shrink-0 place-items-center rounded-full"
      style={{ background: `conic-gradient(${tone} ${score * 3.6}deg, var(--line) 0)` }} title={`Fit score ${score}`}>
      <span className="num grid size-7 place-items-center rounded-full bg-[var(--glass-3)] text-[11px] font-bold text-ink">{score}</span>
    </span>
  );
}

function ContactNext({ i }: { i: Insights }) {
  const navigate = useNavigate();
  const ask = useAiUi((s) => s.ask);
  if (!i.contact_next.length) {
    return <EmptyState icon={<Magnet className="size-5" />} title="Everyone's been contacted"
      body={`Every open lead has had a call, email or meeting in the last ${i.stale_days} days.`} />;
  }
  return (
    <Scroller as="ul" className="flex-1 divide-y divide-[var(--line)]">
      {i.contact_next.map((l) => (
        <li key={l.id} className="group flex items-center gap-3 px-5 py-2.5 hover:bg-[var(--glass-2)]">
          <FitScore score={l.score} />
          <button type="button" onClick={() => navigate(`/leads/${l.id}`)} className="focus-ring min-w-0 flex-1 rounded-lg text-left">
            <p className="truncate text-[13.5px] font-semibold text-ink">{l.name}</p>
            <p className="truncate text-xs text-ink-3">
              {[l.name !== l.company_name ? l.company_name : null, l.industry].filter(Boolean).join(" · ") || "No company"}
              {" · "}{l.last_contact_at ? `last contact ${relative(l.last_contact_at)}` : "never contacted"}
            </p>
          </button>
          <span className="hidden items-center gap-1.5 sm:flex">
            {l.priority ? <Badge tint={l.priority === "High" || l.priority === "Hot" ? "amber" : "slate"} className="h-5 px-2 text-[10px]">{l.priority}</Badge> : null}
            <Mail className={cn("size-3.5", l.has_email ? "text-ink-2" : "text-ink-3 opacity-35")} aria-label={l.has_email ? "Has email" : "No email"} />
            <Phone className={cn("size-3.5", l.has_phone ? "text-ink-2" : "text-ink-3 opacity-35")} aria-label={l.has_phone ? "Has phone" : "No phone"} />
          </span>
          <button
            type="button"
            onClick={() => ask(`Draft a first outreach email to ${l.name}${l.company_name && l.company_name !== l.name ? ` at ${l.company_name}` : ""}. Use what we know about them and why they fit us.`)}
            className="focus-ring flex shrink-0 items-center gap-1.5 rounded-full px-2 py-1 text-[11.5px] font-semibold text-jade transition hover:bg-jade-soft lg:opacity-0 lg:group-hover:opacity-100 lg:focus-visible:opacity-100"
          >
            <Orb className="size-4" /> Draft outreach
          </button>
        </li>
      ))}
    </Scroller>
  );
}

/* ---------------- Lead funnel and fit ---------------- */

function Funnel({ i }: { i: Insights }) {
  const f = i.funnel;
  const steps = [
    { key: "New", n: f.new, tint: "sky" },
    { key: "Contacted", n: f.contacted, tint: "violet" },
    { key: "Qualified", n: f.qualified, tint: "emerald" },
    { key: "Converted", n: f.converted, tint: "amber" },
  ];
  const total = f.new + f.contacted + f.qualified + f.converted + f.unqualified + f.lost;
  const max = Math.max(1, ...steps.map((s) => s.n));
  const bands = [
    { key: "90+", n: i.fit.top, color: "var(--jade)" },
    { key: "80–89", n: i.fit.high, color: "var(--ice)" },
    { key: "70–79", n: i.fit.medium, color: "var(--frost)" },
    { key: "<70", n: i.fit.low, color: "var(--line-strong)" },
  ];
  const open = bands.reduce((a, b) => a + b.n, 0);
  if (!total) {
    return <EmptyState icon={<Magnet className="size-5" />} title="No leads yet" body="Import or add leads to see how they move." />;
  }
  return (
    <div className="flex min-h-0 flex-1 flex-col justify-between gap-3 px-5 pb-4">
      <ul className="space-y-2">
        {steps.map((s, idx) => (
          <li key={s.key} className="grid grid-cols-[78px_1fr_auto] items-center gap-2.5">
            <span className="text-[12.5px] font-semibold text-ink-2">{s.key}</span>
            <span className="h-6 overflow-hidden rounded-lg bg-[var(--line)]">
              <span className={cn("flex h-full min-w-6 items-center rounded-lg px-2 text-[11px] font-bold", tintBg(s.tint))}
                style={{ width: `${(s.n / max) * 100}%` }}>{s.n}</span>
            </span>
            <span className="num w-11 text-right text-[11px] text-ink-3" title={idx ? `Share of leads that got past ${steps[idx - 1].key.toLowerCase()}` : "Share of all leads"}>
              {pct(s.n, total)}%
            </span>
          </li>
        ))}
      </ul>
      <div>
        <div className="mb-1.5 flex items-baseline justify-between text-[11.5px]">
          <span className="font-semibold text-ink-2">Fit of open leads</span>
          <span className="text-ink-3">{f.unqualified + f.lost ? `${f.unqualified} unqualified · ${f.lost} lost` : ""}</span>
        </div>
        <div className="flex h-2.5 overflow-hidden rounded-full bg-[var(--line)]" role="img"
          aria-label={bands.map((b) => `${b.n} with fit ${b.key}`).join(", ")}>
          {bands.map((b) => (b.n ? <span key={b.key} style={{ width: `${pct(b.n, open)}%`, background: b.color }} /> : null))}
        </div>
        <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-ink-3">
          {bands.map((b) => (
            <span key={b.key} className="inline-flex items-center gap-1">
              <span className="size-2 rounded-full" style={{ background: b.color }} />{b.key} <span className="num font-semibold text-ink-2">{b.n}</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ---------------- Today: tasks, agenda, what's gone quiet ---------------- */

function Today({ d }: { d: Dashboard }) {
  const update = taskRes.useUpdate();
  const quiet = d.insights.stale_deals;
  const nothing = !d.my_tasks.length && !d.upcoming_activities.length;
  return (
    <Scroller as="div" className="flex flex-1 flex-col">
      {quiet ? (
        <Link to="/deals?view=list" className="focus-ring mx-5 mb-2 flex items-center gap-2 rounded-xl bg-tint-amber px-3 py-2 text-xs font-semibold text-[#8a5200] dark:text-[#f2c47e]">
          <AlertTriangle className="size-3.5 shrink-0" /> {plural(quiet, "deal")} quiet for {d.insights.stale_days}+ days
        </Link>
      ) : null}
      {nothing ? (
        <EmptyState icon={<CheckSquare className="size-5" />} title="Nothing due today" body="Tasks due today and planned calls or meetings appear here." />
      ) : (
        <ul className="divide-y divide-[var(--line)]">
          {d.my_tasks.map((t) => {
            const overdue = t.due_at && new Date(t.due_at) < new Date();
            return (
              <li key={t.id} className="flex items-center gap-3 px-5 py-2">
                <input type="checkbox" aria-label={`Complete “${t.title}”`} className="size-4 accent-[var(--jade)]"
                  onChange={() => update.mutate({ id: t.id, input: { status: "completed" } })} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-medium">{t.title}</p>
                  <p className={cn("text-[11px]", overdue ? "font-semibold text-danger" : "text-ink-3")}>{t.due_at ? dateTime(t.due_at) : ""}</p>
                </div>
                <Badge tint={TASK_PRIORITY[t.priority].tint} className="h-5 px-2 text-[10px]">{TASK_PRIORITY[t.priority].label}</Badge>
              </li>
            );
          })}
          {d.upcoming_activities.map((a) => (
            <li key={a.id} className="flex items-center gap-3 px-5 py-2">
              <span className="grid size-6 place-items-center rounded-lg bg-tint-sky"><CalendarClock className="size-3.5" /></span>
              <div className="min-w-0">
                <p className="truncate text-[13px] font-medium">{a.subject}</p>
                <p className="text-[11px] text-ink-3">{label(a.type)} · {dateTime(a.occurred_at)}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Scroller>
  );
}

/* ---------------- Team activity: eight weeks ---------------- */

const SERIES = [
  { key: "calls", label: "Calls", color: "var(--ice)" },
  { key: "emails", label: "Emails", color: "var(--frost)" },
  { key: "meetings", label: "Meetings", color: "var(--jade)" },
  { key: "other", label: "Other", color: "var(--line-strong)" },
] as const;

function Activity({ i }: { i: Insights }) {
  const weeks = i.weeks.map((w) => ({ ...w, total: w.calls + w.emails + w.meetings + w.other }));
  const max = Math.max(1, ...weeks.map((w) => w.total));
  const thisWeek = weeks[weeks.length - 1];
  const lastWeek = weeks[weeks.length - 2];
  const fmt = (iso: string) => new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" }).format(new Date(iso));
  if (!weeks.some((w) => w.total)) {
    return <EmptyState icon={<Phone className="size-5" />} title="No calls, emails or meetings yet"
      body="Log outreach from any lead or company and the weekly rhythm shows up here." action={<LogActivityButton />} />;
  }
  const delta = thisWeek.total - (lastWeek?.total ?? 0);
  return (
    <div className="flex min-h-0 flex-1 flex-col px-5 pb-4">
      <p className="mb-2 text-xs text-ink-3">
        <span className="num font-semibold text-ink">{thisWeek.total}</span> this week
        {lastWeek ? <> · <span className={cn("num font-semibold", delta > 0 ? "text-jade" : delta < 0 ? "text-danger" : "text-ink-2")}>{delta > 0 ? "+" : ""}{delta}</span> vs last week</> : null}
      </p>
      <div className="flex min-h-16 flex-1 items-end gap-1.5" role="img"
        aria-label={weeks.map((w) => `Week of ${fmt(w.week_start)}: ${w.total}`).join(", ")}>
        {weeks.map((w) => (
          <div key={w.week_start} className="flex h-full flex-1 flex-col items-center justify-end gap-1"
            title={`${fmt(w.week_start)}: ${w.calls} calls, ${w.emails} emails, ${w.meetings} meetings, ${w.other} other`}>
            <div className="flex w-full max-w-9 flex-col-reverse overflow-hidden rounded-md" style={{ height: `${Math.max(4, (w.total / max) * 100)}%` }}>
              {w.total ? SERIES.map((s) => (w[s.key] ? <span key={s.key} style={{ flexGrow: w[s.key], background: s.color }} /> : null))
                : <span className="h-full bg-[var(--line)]" />}
            </div>
            <span className="num text-[10px] whitespace-nowrap text-ink-3">{fmt(w.week_start)}</span>
          </div>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-3 text-[11px] text-ink-3">
        {SERIES.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-1"><span className="size-2 rounded-full" style={{ background: s.color }} />{s.label}</span>
        ))}
      </div>
    </div>
  );
}

/* ---------------- Where prospects are ---------------- */

function Where({ i }: { i: Insights }) {
  const [by, setBy] = useState<"cities" | "industries">("cities");
  const rows = i[by];
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <div className="flex min-h-0 flex-1 flex-col px-5 pb-4">
      <div className="mb-2 inline-flex w-fit gap-1 rounded-full bg-[var(--line)] p-0.5" role="group" aria-label="Group prospects by">
        {(["cities", "industries"] as const).map((k) => (
          <button key={k} type="button" aria-pressed={by === k} onClick={() => setBy(k)}
            className={cn("focus-ring h-6 rounded-full px-2.5 text-[11.5px] font-semibold text-ink-2", by === k && "bg-[var(--glass-3)] text-ink shadow-sm")}>
            {k === "cities" ? "City" : "Industry"}
          </button>
        ))}
      </div>
      {rows.length ? (
        <Scroller as="ul" className="flex-1 space-y-1.5">
          {rows.map((r) => (
            <li key={r.label} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2">
              <span className="relative h-6 overflow-hidden rounded-lg bg-[var(--line)]">
                <span className="absolute inset-y-0 left-0 rounded-lg bg-jade-soft" style={{ width: `${(r.count / max) * 100}%` }} />
                <span className="relative block truncate px-2 text-[12px] leading-6 font-medium text-ink">{r.label}</span>
              </span>
              <span className="num w-8 text-right text-[12px] font-semibold text-ink-2">{r.count}</span>
            </li>
          ))}
        </Scroller>
      ) : (
        <p className="text-xs text-ink-3">No prospect companies yet.</p>
      )}
    </div>
  );
}

/* ---------------- Pipeline by stage ---------------- */

function Pipeline({ d }: { d: Dashboard }) {
  const stages = d.pipeline.stages.filter((s) => s.kind === "open");
  const max = Math.max(1, ...stages.map((s) => s.count));
  if (!stages.some((s) => s.count)) {
    return <EmptyState icon={<Handshake className="size-5" />} title="No open deals yet"
      body="Convert a qualified lead to open its first deal." action={<Link to="/leads"><Button size="sm">Go to leads</Button></Link>} />;
  }
  return (
    <Scroller as="ul" className="flex-1 space-y-1.5 px-5 pb-4">
      {stages.map((s) => (
        <li key={s.stage_id} className="grid grid-cols-[84px_1fr_auto] items-center gap-2">
          <span className="truncate text-[12px] font-semibold text-ink-2">{s.name}</span>
          <span className="h-5 overflow-hidden rounded-md bg-[var(--line)]">
            <span className={cn("flex h-full min-w-5 items-center rounded-md px-1.5 text-[10.5px] font-bold", tintBg(s.color))}
              style={{ width: `${(s.count / max) * 100}%` }}>{s.count}</span>
          </span>
          <span className="num w-14 text-right text-[11.5px] font-semibold text-ink">{money(s.amount, d.currency, { compact: true })}</span>
        </li>
      ))}
    </Scroller>
  );
}

/* ---------------- Page ---------------- */

const link = "text-xs font-semibold text-jade hover:underline";

export function DashboardPage() {
  const me = useAuth((s) => s.me);
  const canWrite = useCan("crm:write");
  const ask = useAiUi((s) => s.ask);
  const { data: d, isLoading, error, refetch } = useDashboard(timeZone());
  const first = me?.full_name.split(" ")[0];
  const today = new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long" }).format(new Date());

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="rise mb-3 flex flex-none flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13px] font-semibold text-ink-3">{today}</p>
          <h1 className="mt-0.5 font-display text-[26px] leading-tight font-bold tracking-[-0.035em] md:text-[30px] [@media(max-height:760px)]:md:text-[24px]">
            {greeting()}{first ? `, ${first}` : ""}.
          </h1>
          {d ? (
            <p className="mt-0.5 truncate text-sm text-ink-2">
              {d.insights.to_contact
                ? `${plural(d.insights.to_contact, "lead")} waiting for a first touch${d.insights.fit.top ? `, ${d.insights.fit.top} with fit 90+` : ""}.`
                : "Every open lead has been contacted recently."}{" "}
              {d.tasks.due_today + d.tasks.overdue ? `${plural(d.tasks.due_today + d.tasks.overdue, "task")} need you today.` : ""}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" icon={<Orb className="size-4" />}
            onClick={() => ask("Give me a short briefing for today: what needs my attention across leads, deals and tasks, and which three prospects I should contact first and why.")}>
            Brief me
          </Button>
          {canWrite ? (
            <>
              <LogActivityButton />
              <Link to="/leads"><Button variant="primary" icon={<Plus className="size-4" />}>Add lead</Button></Link>
            </>
          ) : null}
        </div>
      </div>

      {error ? (
        <Card><ErrorState message={describeError(error)} onRetry={() => refetch()} /></Card>
      ) : isLoading || !d ? (
        <div className="grid flex-none grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          {[0, 1, 2, 3, 4, 5].map((n) => <Skeleton key={n} className="h-[104px] rounded-[20px]" />)}
        </div>
      ) : (
        <>
          <Headline d={d} />
          {d.pipeline.other_currency_deals ? (
            <p className="mt-1.5 flex-none text-[11px] text-ink-3">
              Money totals are in {d.currency}; {plural(d.pipeline.other_currency_deals, "deal")} in other currencies {d.pipeline.other_currency_deals === 1 ? "is" : "are"} left out.
            </p>
          ) : null}

          <div className="rise mt-3 grid gap-3 lg:min-h-0 lg:flex-1 lg:grid-cols-12 lg:grid-rows-[minmax(0,1.2fr)_minmax(0,1fr)]" style={{ animationDelay: "90ms" }}>
            <Card className={PANEL + " lg:col-span-5"}>
              <CardHeader title="Contact next"
                subtitle={`Best-fit leads with no contact in ${d.insights.stale_days} days · ${d.insights.to_contact} in all`}
                action={<Link to="/leads" className={link}>All leads</Link>} />
              <ContactNext i={d.insights} />
            </Card>
            <Card className={PANEL + " lg:col-span-4"}>
              <CardHeader title="Lead funnel" subtitle="Where every lead stands, as a share of all leads"
                action={<Link to="/leads" className={link}>Open</Link>} />
              <Funnel i={d.insights} />
            </Card>
            <Card className={PANEL + " lg:col-span-3"}>
              <CardHeader title="Today" subtitle="Your tasks and what's planned"
                action={<Link to="/tasks" className={link}>All tasks</Link>} />
              <Today d={d} />
            </Card>

            <Card className={PANEL + " lg:col-span-5"}>
              <CardHeader title="Team activity" subtitle="Calls, emails and meetings logged, last 8 weeks"
                action={<Link to="/activities" className={link}>All</Link>} />
              <Activity i={d.insights} />
            </Card>
            <Card className={PANEL + " lg:col-span-4"}>
              <CardHeader title="Where your prospects are"
                subtitle={`${d.insights.coverage.companies} prospect companies`}
                action={<Link to="/companies" className={link}>Companies</Link>} />
              <Where i={d.insights} />
            </Card>
            <Card className={PANEL + " lg:col-span-3"}>
              <CardHeader title="Pipeline" subtitle={`${plural(d.pipeline.open_deals, "open deal")} by stage`}
                action={<Link to="/deals" className={link}>Board</Link>} />
              <Pipeline d={d} />
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
