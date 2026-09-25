import { ArrowUpRight, CalendarClock, CheckSquare, Plus } from "lucide-react";
import { Link } from "react-router-dom";

import { LogActivityButton } from "@/components/data/Related";
import { Avatar, Badge, Button, Card, CardHeader, EmptyState, ErrorState, Skeleton, tintBg } from "@/components/ui/primitives";
import { tasks as taskRes, useDashboard } from "@/hooks/resources";
import { cn, dateTime, label, money, relative, timeZone } from "@/lib/format";
import { DEAL_STATUS, TASK_PRIORITY } from "@/lib/status";
import { describeError } from "@/services/api";
import { useAuth, useCan } from "@/stores/auth";
import type { Dashboard } from "@/types";

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

/** Pastel headline tiles, echoing stage cards: tint, figure, context line, one meter. */
function Tile({ tint, title, value, detail, meter, to }: {
  tint: string; title: string; value: string; detail: string; meter?: number; to: string;
}) {
  return (
    <Link
      to={to}
      className={cn(
        "focus-ring group relative overflow-hidden rounded-[var(--radius-card)] border border-[var(--glass-edge)] p-4 transition hover:-translate-y-0.5",
        tintBg(tint),
      )}
    >
      <div className="flex items-start justify-between">
        <p className="text-[13px] font-semibold opacity-80">{title}</p>
        <ArrowUpRight className="size-4 opacity-0 transition group-hover:opacity-70" />
      </div>
      <p className="num mt-3 text-[30px] leading-none font-extrabold tracking-[-0.04em] text-ink">{value}</p>
      <p className="mt-2 text-xs font-medium opacity-80">{detail}</p>
      {meter !== undefined ? (
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/50 dark:bg-white/10">
          <div className="h-full rounded-full bg-current opacity-70" style={{ width: `${Math.min(100, Math.max(0, meter))}%` }} />
        </div>
      ) : null}
    </Link>
  );
}

function PipelineByStage({ d }: { d: Dashboard }) {
  const stages = d.pipeline.stages.filter((s) => s.kind === "open");
  const max = Math.max(1, ...stages.map((s) => s.amount));
  if (!stages.some((s) => s.count)) {
    return <EmptyState title="No open deals yet" body="Deals you create or convert from leads will fill this chart." action={<Link to="/deals"><Button size="sm">Open pipeline</Button></Link>} />;
  }
  return (
    <ul className="space-y-3 px-5 pb-5">
      {stages.map((s) => (
        <li key={s.stage_id} className="grid grid-cols-[110px_1fr_auto] items-center gap-3">
          <span className="truncate text-sm font-semibold">{s.name}</span>
          <span className="h-7 overflow-hidden rounded-full bg-[var(--line)]">
            <span
              className={cn("flex h-full min-w-7 items-center rounded-full px-2.5 text-[11px] font-bold", tintBg(s.color))}
              style={{ width: `${(s.amount / max) * 100}%` }}
            >
              {s.count}
            </span>
          </span>
          <span className="num w-20 text-right text-sm font-semibold">{money(s.amount, d.currency, { compact: true })}</span>
        </li>
      ))}
    </ul>
  );
}

function MyTasks({ d }: { d: Dashboard }) {
  const update = taskRes.useUpdate();
  if (!d.my_tasks.length) {
    return <EmptyState icon={<CheckSquare className="size-5" />} title="Nothing due today" body="Tasks due today or overdue will appear here." />;
  }
  return (
    <ul className="divide-y divide-[var(--line)]">
      {d.my_tasks.map((t) => {
        const overdue = t.due_at && new Date(t.due_at) < new Date();
        return (
          <li key={t.id} className="flex items-center gap-3 px-5 py-2.5">
            <input
              type="checkbox"
              aria-label={`Complete “${t.title}”`}
              onChange={() => update.mutate({ id: t.id, input: { status: "completed" } })}
              className="size-4 accent-[var(--jade)]"
            />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{t.title}</p>
              <p className={cn("text-xs", overdue ? "font-semibold text-danger" : "text-ink-3")}>{t.due_at ? dateTime(t.due_at) : ""}</p>
            </div>
            <Badge tint={TASK_PRIORITY[t.priority].tint}>{TASK_PRIORITY[t.priority].label}</Badge>
          </li>
        );
      })}
    </ul>
  );
}

export function DashboardPage() {
  const me = useAuth((s) => s.me);
  const canWrite = useCan("crm:write");
  const { data: d, isLoading, error, refetch } = useDashboard(timeZone());
  const first = me?.full_name.split(" ")[0];
  const today = new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long" }).format(new Date());

  return (
    <div>
      <div className="rise mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-ink-3">{today}</p>
          <h1 className="mt-1 text-[32px] leading-tight font-extrabold tracking-[-0.035em] md:text-[40px]">
            {greeting()}, {first}.
          </h1>
          {d ? (
            <p className="mt-1 text-sm text-ink-2">
              {d.tasks.due_today + d.tasks.overdue > 0
                ? `${d.tasks.due_today} task${d.tasks.due_today === 1 ? "" : "s"} due today${d.tasks.overdue ? `, ${d.tasks.overdue} overdue` : ""}.`
                : "No tasks due today."}{" "}
              {d.pipeline.closing_this_month ? `${d.pipeline.closing_this_month} deal${d.pipeline.closing_this_month === 1 ? "" : "s"} expected to close this month.` : ""}
            </p>
          ) : null}
        </div>
        {canWrite ? (
          <div className="flex gap-2">
            <LogActivityButton />
            <Link to="/leads"><Button variant="primary" icon={<Plus className="size-4" />}>Add lead</Button></Link>
          </div>
        ) : null}
      </div>

      {error ? (
        <Card><ErrorState message={describeError(error)} onRetry={() => refetch()} /></Card>
      ) : isLoading || !d ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-36 rounded-[22px]" />)}</div>
      ) : (
        <>
          <div className="rise grid gap-4 md:grid-cols-2 xl:grid-cols-4" style={{ animationDelay: "40ms" }}>
            <Tile tint="amber" to="/deals" title="Open pipeline" value={money(d.pipeline.pipeline_value, d.currency, { compact: true })}
              detail={`${d.pipeline.open_deals} open deal${d.pipeline.open_deals === 1 ? "" : "s"}`} />
            <Tile tint="sky" to="/deals?view=list" title="Weighted forecast" value={money(d.pipeline.weighted_value, d.currency, { compact: true })}
              detail="Amount × probability, open deals" meter={d.pipeline.pipeline_value ? (d.pipeline.weighted_value / d.pipeline.pipeline_value) * 100 : 0} />
            <Tile tint="emerald" to="/deals?view=list&status=won" title="Won this month" value={money(d.pipeline.revenue_this_month, d.currency, { compact: true })}
              detail={`${money(d.pipeline.revenue_total, d.currency, { compact: true })} won all time · ${d.pipeline.won_deals} won, ${d.pipeline.lost_deals} lost`} />
            <Tile tint="rose" to="/leads" title="Leads" value={String(d.leads.total)}
              detail={`${d.leads.new_last_30_days} new in 30 days · ${d.leads.qualified} qualified`}
              meter={d.leads.total ? (d.leads.converted / d.leads.total) * 100 : 0} />
          </div>
          {d.pipeline.other_currency_deals ? (
            <p className="mt-2 text-xs text-ink-3">Totals are in {d.currency}; {d.pipeline.other_currency_deals} deal{d.pipeline.other_currency_deals === 1 ? " is" : "s are"} in other currencies and not included.</p>
          ) : null}

          <div className="rise mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]" style={{ animationDelay: "90ms" }}>
            <Card>
              <CardHeader title="Pipeline by stage" subtitle="Open deals and their value" action={<Link to="/deals" className="text-xs font-semibold text-jade hover:underline">View board</Link>} />
              <PipelineByStage d={d} />
            </Card>
            <Card>
              <CardHeader title="My tasks" subtitle="Due today and overdue" action={<Link to="/tasks" className="text-xs font-semibold text-jade hover:underline">All tasks</Link>} />
              <MyTasks d={d} />
            </Card>
          </div>

          <div className="rise mt-4 grid gap-4 lg:grid-cols-3" style={{ animationDelay: "140ms" }}>
            <Card>
              <CardHeader title="Recent activity" action={<Link to="/activities" className="text-xs font-semibold text-jade hover:underline">All</Link>} />
              {d.recent_activities.length ? (
                <ul className="divide-y divide-[var(--line)]">
                  {d.recent_activities.map((a) => (
                    <li key={a.id} className="px-5 py-2.5">
                      <p className="truncate text-sm font-medium">{a.subject}</p>
                      <p className="text-xs text-ink-3">{label(a.type)} · {relative(a.occurred_at)}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState title="No activity yet" body="Logged calls, meetings and stage changes show up here." />
              )}
            </Card>
            <Card>
              <CardHeader title="Coming up" subtitle="Planned calls and meetings" />
              {d.upcoming_activities.length ? (
                <ul className="divide-y divide-[var(--line)]">
                  {d.upcoming_activities.map((a) => (
                    <li key={a.id} className="flex items-center gap-3 px-5 py-2.5">
                      <span className="flex size-8 items-center justify-center rounded-xl bg-tint-sky"><CalendarClock className="size-4" /></span>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">{a.subject}</p>
                        <p className="text-xs text-ink-3">{dateTime(a.occurred_at)}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState title="Nothing scheduled" body="Log an activity with a future time to plan it." />
              )}
            </Card>
            <Card>
              <CardHeader title="Recently added" />
              <ul className="divide-y divide-[var(--line)]">
                {d.recent_deals.slice(0, 3).map((x) => (
                  <li key={x.id}>
                    <Link to={`/deals/${x.id}`} className="focus-ring flex items-center gap-3 px-5 py-2.5 hover:bg-[var(--glass-2)]">
                      <Badge tint={DEAL_STATUS[x.status].tint}>Deal</Badge>
                      <span className="min-w-0 flex-1 truncate text-sm font-medium">{x.name}</span>
                      <span className="num text-xs text-ink-2">{money(x.amount, x.currency, { compact: true })}</span>
                    </Link>
                  </li>
                ))}
                {d.recent_companies.slice(0, 3).map((x) => (
                  <li key={x.id}>
                    <Link to={`/companies/${x.id}`} className="focus-ring flex items-center gap-3 px-5 py-2.5 hover:bg-[var(--glass-2)]">
                      <Badge tint="violet">Company</Badge>
                      <span className="min-w-0 flex-1 truncate text-sm font-medium">{x.name}</span>
                    </Link>
                  </li>
                ))}
                {d.recent_contacts.slice(0, 3).map((x) => (
                  <li key={x.id}>
                    <Link to={`/contacts/${x.id}`} className="focus-ring flex items-center gap-3 px-5 py-2.5 hover:bg-[var(--glass-2)]">
                      <Avatar name={x.full_name} size={24} />
                      <span className="min-w-0 flex-1 truncate text-sm font-medium">{x.full_name}</span>
                    </Link>
                  </li>
                ))}
              </ul>
              {!d.recent_deals.length && !d.recent_companies.length && !d.recent_contacts.length ? (
                <EmptyState title="Nothing added yet" body="New deals, companies and contacts appear here." />
              ) : null}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
