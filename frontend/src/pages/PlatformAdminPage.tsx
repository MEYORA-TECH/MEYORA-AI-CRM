import * as Tabs from "@radix-ui/react-tabs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import {
  AlertTriangle, Building2, Check, Copy, ExternalLink, Globe, KeyRound, LockKeyhole, Mail, RefreshCw, ShieldCheck,
  Sparkles, UsersRound,
} from "@/components/icons";
import { ConfirmDialog } from "@/components/ui/overlay";
import { Scroller } from "@/components/ui/Scroller";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorState, Input, Skeleton, tintBg } from "@/components/ui/primitives";
import { PageHeader } from "@/layouts/AppShell";
import { cn, relative, timeZone } from "@/lib/format";
import { api, describeError } from "@/services/api";
import { useAuth } from "@/stores/auth";
import type { components } from "@/types/api";

type Overview = components["schemas"]["OverviewOut"];
type Settings = components["schemas"]["SettingsOut"];
type SharedKey = components["schemas"]["SharedKeyOut"];

const SETTINGS = ["platform", "settings"];
const compact = (n: number) => new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(n);
const PANEL = "flex flex-col overflow-hidden lg:min-h-0";

function useSettings() {
  return useQuery({ queryKey: SETTINGS, queryFn: () => api.get<Settings>("/platform/settings") });
}

/* ================= Overview ================= */

function Stat({ icon, tint, label, value, sub }: { icon: ReactNode; tint: string; label: string; value: string; sub: string }) {
  return (
    <div className="glass flex min-w-0 flex-col rounded-[20px] p-3.5">
      <div className="flex items-center gap-2">
        <span className={cn("grid size-7 shrink-0 place-items-center rounded-lg", tintBg(tint))}>{icon}</span>
        <span className="truncate text-[12.5px] font-semibold text-ink-2">{label}</span>
      </div>
      <p className="num mt-2 truncate font-display text-[24px] leading-none font-bold tracking-[-0.03em]">{value}</p>
      <p className="mt-1.5 truncate text-[11.5px] text-ink-3">{sub}</p>
    </div>
  );
}

function Pill({ ok, children }: { ok: boolean; children: ReactNode }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold",
      ok ? "bg-tint-emerald text-[#17634a] dark:text-[#8fe0c0]" : "bg-tint-slate text-ink-2")}>
      <span className={cn("size-1.5 rounded-full", ok ? "bg-[#1f9d6b]" : "bg-ink-3")} />{children}
    </span>
  );
}

function OverviewTab() {
  const q = useQuery({
    queryKey: ["platform", "overview"],
    queryFn: () => api.get<Overview>("/platform/overview", { tz: timeZone() }),
    refetchInterval: 60_000,
  });
  if (q.error) return <Card><ErrorState message={describeError(q.error)} onRetry={() => q.refetch()} /></Card>;
  if (!q.data) {
    return <div className="grid grid-cols-2 gap-3 xl:grid-cols-6">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-[96px] rounded-[20px]" />)}</div>;
  }
  const o = q.data;
  const max = Math.max(1, ...o.daily_tokens.map((d) => d.tokens));
  const providerTotal = o.providers.reduce((a, p) => a + p.tokens, 0);
  const queued = o.jobs.queued ?? 0;
  const failed = o.jobs.failed ?? 0;
  const day = (iso: string) => new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" }).format(new Date(iso));

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="grid flex-none grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat icon={<Building2 className="size-4" />} tint="violet" label="Workspaces" value={String(o.workspaces)} sub={`${o.environment} environment`} />
        <Stat icon={<UsersRound className="size-4" />} tint="sky" label="Users" value={String(o.users)}
          sub={`${o.active_users_7d} active in 7 days · ${o.new_users_30d} new in 30`} />
        <Stat icon={<Sparkles className="size-4" />} tint="emerald" label="AI tokens today" value={compact(o.ai_tokens_today)}
          sub={`${compact(o.ai_tokens_30d)} in 30 days`} />
        <Stat icon={<Globe className="size-4" />} tint="amber" label="Web searches" value={String(o.web_searches_month)}
          sub={`this month · limit ${o.web_monthly_limit_per_workspace} per workspace`} />
        <Stat icon={<Mail className="size-4" />} tint="slate" label="Mailboxes" value={String(o.mailboxes)} sub="Gmail accounts connected" />
        <Stat icon={<RefreshCw className="size-4" />} tint={o.failed_jobs_24h ? "rose" : "slate"} label="Background jobs"
          value={String(queued)} sub={`queued · ${o.failed_jobs_24h} failed in 24h · ${failed} failed total`} />
      </div>

      <div className="grid gap-3 lg:min-h-0 lg:flex-1 lg:grid-cols-12 lg:grid-rows-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <Card className={PANEL + " lg:col-span-6"}>
          <CardHeader title="AI usage" subtitle="Tokens per day across all workspaces, last 14 days" />
          <div className="flex min-h-0 flex-1 flex-col px-5 pb-4">
            <div className="flex min-h-16 flex-1 items-end gap-1" role="img" aria-label={o.daily_tokens.map((d) => `${day(d.day)}: ${d.tokens}`).join(", ")}>
              {o.daily_tokens.map((d) => (
                <div key={d.day} className="flex h-full flex-1 flex-col items-center justify-end gap-1" title={`${day(d.day)}: ${d.tokens.toLocaleString("en-IN")} tokens`}>
                  <span className={cn("w-full max-w-7 rounded-md", d.tokens ? "bg-ice" : "bg-[var(--line)]")} style={{ height: `${Math.max(3, (d.tokens / max) * 100)}%` }} />
                  <span className="num text-[9.5px] text-ink-3">{day(d.day).split(" ")[0]}</span>
                </div>
              ))}
            </div>
            <p className="mt-2 text-[11px] text-ink-3">Daily limit per user: {compact(o.ai_daily_quota_per_user)} tokens.</p>
          </div>
        </Card>
        <Card className={PANEL + " lg:col-span-3"}>
          <CardHeader title="By provider" subtitle="Last 30 days" />
          {o.providers.length ? (
            <Scroller as="ul" className="flex-1 space-y-2 px-5 pb-4">
              {o.providers.map((p) => (
                <li key={p.provider}>
                  <div className="flex justify-between text-[12.5px]"><span className="font-semibold capitalize">{p.provider}</span>
                    <span className="num text-ink-2">{compact(p.tokens)} · {Math.round((p.tokens / providerTotal) * 100)}%</span></div>
                  <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-[var(--line)]">
                    <span className="block h-full rounded-full bg-ice" style={{ width: `${(p.tokens / providerTotal) * 100}%` }} />
                  </span>
                </li>
              ))}
            </Scroller>
          ) : <EmptyState title="No AI use yet" body="Calls to any AI provider show up here." />}
        </Card>
        <Card className={PANEL + " lg:col-span-3"}>
          <CardHeader title="Health" subtitle={`Checked ${relative(o.generated_at)}`} />
          <ul className="min-h-0 flex-1 space-y-2.5 overflow-hidden px-5 pb-4 text-[12.5px]">
            <li className="flex items-center justify-between gap-2"><span className="text-ink-2">Database</span>
              <Pill ok={o.db_latency_ms < 300}>{o.db_latency_ms} ms per query</Pill></li>
            <li className="flex items-center justify-between gap-2"><span className="text-ink-2">Sign in with Google</span>
              <Pill ok={o.health.sign_in_live}>{o.health.sign_in_live ? "On" : o.health.google_ready ? "Off" : "Not set up"}</Pill></li>
            <li className="flex items-center justify-between gap-2"><span className="text-ink-2">Gmail sync</span>
              <Pill ok={o.health.gmail_live}>{o.health.gmail_live ? "On" : o.health.google_ready ? "Off" : "Not set up"}</Pill></li>
            <li>
              <span className="text-ink-2">Shared keys</span>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {Object.entries(o.health.shared_keys).map(([p, ok]) => <Pill key={p} ok={ok}><span className="capitalize">{p}</span></Pill>)}
              </div>
            </li>
            {o.failed_jobs_24h ? (
              <li className="flex items-center gap-2 rounded-xl bg-tint-rose px-2.5 py-1.5 font-semibold text-[#9b1f45] dark:text-[#f5a3ba]">
                <AlertTriangle className="size-3.5" /> {o.failed_jobs_24h} jobs failed in the last day
              </li>
            ) : null}
          </ul>
        </Card>

        <Card className={PANEL + " lg:col-span-9"}>
          <CardHeader title="Workspaces" subtitle="Totals only; records stay inside each workspace" />
          <div className="scroll-quiet min-h-0 flex-1 overflow-auto">
            <table className="w-full min-w-[640px] text-left text-[12.5px]">
              <thead className="sticky top-0 bg-[var(--glass-3)] text-[11px] font-semibold text-ink-3">
                <tr className="border-y border-line">
                  {["Workspace", "Members", "Companies", "Leads", "Open deals", "AI (30 days)", "Web (month)", "Mailboxes", "Last activity"].map((h, i) => (
                    <th key={h} className={cn("px-4 py-2 whitespace-nowrap", i > 0 && i < 8 && "text-right")}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {o.workspace_list.map((w) => (
                  <tr key={w.id} className="border-b border-line last:border-0">
                    <td className="px-4 py-2.5"><p className="font-semibold">{w.name}</p><p className="text-[11px] text-ink-3">since {relative(w.created_at)}</p></td>
                    {[w.members, w.companies, w.leads, w.deals_open].map((n, i) => <td key={i} className="num px-4 text-right">{n}</td>)}
                    <td className="num px-4 text-right">{compact(w.ai_tokens_30d)}</td>
                    <td className="num px-4 text-right">{w.web_searches_month}</td>
                    <td className="num px-4 text-right">{w.mailboxes}</td>
                    <td className="px-4 whitespace-nowrap text-ink-2">{w.last_activity_at ? relative(w.last_activity_at) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card className={PANEL + " lg:col-span-3"}>
          <CardHeader title="Newest users" />
          <Scroller as="ul" className="flex-1 divide-y divide-[var(--line)]">
            {o.recent_users.map((u) => (
              <li key={u.email} className="px-5 py-2">
                <p className="truncate text-[13px] font-semibold">{u.full_name}</p>
                <p className="truncate text-[11px] text-ink-3">{u.email} · joined {relative(u.created_at)}</p>
              </li>
            ))}
          </Scroller>
        </Card>
      </div>
    </div>
  );
}

/* ================= Google & Gmail ================= */

function SourceNote({ source }: { source: "saved" | "server" | null | undefined }) {
  if (source === "server") return <span className="text-[11px] text-ink-3">from the server's environment</span>;
  if (source === "saved") return <span className="text-[11px] text-ink-3">saved here</span>;
  return null;
}

function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled} onClick={() => onChange(!checked)}
      className={cn("focus-ring relative h-6 w-11 shrink-0 rounded-full transition disabled:opacity-40", checked ? "bg-jade" : "bg-[var(--line-strong)]")}>
      <span className={cn("absolute top-0.5 left-0.5 size-5 rounded-full bg-white shadow transition", checked && "translate-x-5")} />
    </button>
  );
}

function CopyRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-40 shrink-0 text-xs text-ink-3">{label}</span>
      <code className="min-w-0 flex-1 truncate rounded-lg bg-[var(--line)] px-2 py-1 font-mono text-[11.5px]">{value}</code>
      <button type="button" aria-label={`Copy ${label}`} className="focus-ring rounded-lg p-1.5 text-ink-3 hover:text-ink"
        onClick={async () => { await navigator.clipboard.writeText(value).catch(() => undefined); toast.success("Copied"); }}>
        <Copy className="size-3.5" />
      </button>
    </div>
  );
}

function GoogleTab() {
  const qc = useQueryClient();
  const s = useSettings();
  const [clientId, setClientId] = useState("");
  const [secret, setSecret] = useState("");
  const [clearing, setClearing] = useState(false);
  useEffect(() => { if (s.data) setClientId(s.data.google.client_id ?? ""); }, [s.data]);

  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.put<Settings>("/platform/google", body),
    onSuccess: (data) => {
      qc.setQueryData(SETTINGS, data);
      qc.invalidateQueries({ queryKey: ["platform", "overview"] });
      qc.invalidateQueries({ queryKey: ["auth", "providers"] });
      setSecret("");
      toast.success("Google settings saved");
    },
    onError: (e) => toast.error(describeError(e)),
  });

  if (s.error) return <Card><ErrorState message={describeError(s.error)} onRetry={() => s.refetch()} /></Card>;
  if (!s.data) return <Skeleton className="h-96 rounded-[22px]" />;
  const g = s.data.google;

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
      <Card>
        <CardHeader title="Google OAuth client" subtitle="One client for the whole installation: it signs people in and connects Gmail." />
        <form className="space-y-4 px-5 pb-5" onSubmit={(e) => {
          e.preventDefault();
          save.mutate({ client_id: clientId.trim() || null, ...(secret.trim() ? { client_secret: secret.trim() } : {}) });
        }}>
          <label className="block">
            <span className="flex items-center justify-between text-[13px] font-semibold">Client ID <SourceNote source={g.client_id_source} /></span>
            <Input className="mt-1.5 font-mono text-[12.5px]" value={clientId} onChange={(e) => setClientId(e.target.value)}
              placeholder="1234567890-abc.apps.googleusercontent.com" spellCheck={false} />
          </label>
          <label className="block">
            <span className="flex items-center justify-between text-[13px] font-semibold">Client secret <SourceNote source={g.secret_source} /></span>
            <Input type="password" autoComplete="off" className="mt-1.5 font-mono text-[12.5px]" value={secret} onChange={(e) => setSecret(e.target.value)}
              placeholder={g.secret_set ? `Saved ••••${g.secret_last4} — paste a new one to replace it` : "GOCSPX-…"} spellCheck={false} />
            <span className="mt-1 flex items-center gap-1.5 text-[11px] text-ink-3"><LockKeyhole className="size-3" /> Stored encrypted. It's never shown again.</span>
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" variant="primary" loading={save.isPending}>Save client</Button>
            {g.secret_source === "saved" ? <Button type="button" variant="ghost" onClick={() => setClearing(true)}>Remove saved secret</Button> : null}
            {g.ready ? <Badge tint="emerald">Client ready</Badge> : <Badge tint="amber">Needs a client ID and secret</Badge>}
          </div>
        </form>

        <div className="divide-y divide-[var(--line)] border-t border-line">
          {([
            { key: "sign_in_enabled", title: "Sign in with Google", body: "Show “Continue with Google” on the sign-in page. Email and password keep working either way.", on: g.sign_in_switch, live: g.sign_in_live, source: g.sign_in_source },
            { key: "gmail_enabled", title: "Gmail sync", body: "Let people connect their Gmail in Settings → Email. Only mail with CRM contacts is stored.", on: g.gmail_switch, live: g.gmail_live, source: g.gmail_source },
          ] as const).map((row) => (
            <div key={row.key} className="flex items-start gap-4 px-5 py-4">
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-2 text-sm font-semibold">{row.title}
                  {row.live ? <Pill ok>Live</Pill> : row.on ? <Pill ok={false}>Waiting for the client</Pill> : null}</p>
                <p className="mt-0.5 text-[12.5px] text-ink-3">{row.body}</p>
                <SourceNote source={row.source} />
              </div>
              <Switch label={row.title} checked={row.on} disabled={save.isPending} onChange={(v) => save.mutate({ [row.key]: v })} />
            </div>
          ))}
        </div>
      </Card>

      <Card className="h-fit">
        <CardHeader title="Set up in Google Cloud" subtitle="Five minutes, once." />
        <ol className="list-decimal space-y-2.5 px-5 pb-4 pl-9 text-[12.5px] text-ink-2">
          <li>Open <a className="font-semibold text-jade hover:underline" href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener noreferrer">Google Cloud → Credentials <ExternalLink className="inline size-3" /></a> and create an <b>OAuth client ID</b> of type <b>Web application</b>.</li>
          <li>Add the origin and redirect URIs below exactly as shown.</li>
          <li>For Gmail, enable the <b>Gmail API</b> and add the scopes <code className="font-mono text-[11px]">gmail.readonly</code> and <code className="font-mono text-[11px]">gmail.send</code> on the consent screen.</li>
          <li>Paste the client ID and secret here, save, then turn on what you need.</li>
        </ol>
        <div className="space-y-1.5 border-t border-line px-5 py-4">
          <CopyRow label="JavaScript origin" value={g.javascript_origin} />
          <CopyRow label="Redirect URI (sign-in)" value={g.redirect_uris.sign_in} />
          <CopyRow label="Redirect URI (Gmail)" value={g.redirect_uris.gmail} />
          <p className="pt-1 text-[11px] text-ink-3">These use the server's PUBLIC_URL. When you deploy, add the production addresses too.</p>
        </div>
      </Card>

      <ConfirmDialog open={clearing} onOpenChange={setClearing} title="Remove the saved client secret?"
        description="Google sign-in and Gmail stop working unless the server's environment has a secret."
        confirmLabel="Remove secret" loading={save.isPending}
        onConfirm={async () => { await save.mutateAsync({ client_secret: null }); setClearing(false); }} />
    </div>
  );
}

/* ================= Shared keys ================= */

function SharedKeyRow({ item }: { item: SharedKey }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const done = (data?: Settings) => {
    if (data) qc.setQueryData(SETTINGS, data); else qc.invalidateQueries({ queryKey: SETTINGS });
    qc.invalidateQueries({ queryKey: ["platform", "overview"] });
    qc.invalidateQueries({ queryKey: ["ai", "status"] });
  };
  const save = useMutation({
    mutationFn: () => api.put<Settings>(`/platform/keys/${item.provider}`, { value }),
    onSuccess: (data) => { done(data); setEditing(false); setValue(""); toast.success(`${item.label} shared key saved`); },
  });
  const remove = useMutation({
    mutationFn: () => api.delete(`/platform/keys/${item.provider}`),
    onSuccess: () => { done(); toast.success(`${item.label} shared key removed`); },
    onError: (e) => toast.error(describeError(e)),
  });
  return (
    <li className="px-5 py-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-glass-2 text-ink-2"><KeyRound className="size-4" /></span>
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 font-semibold">{item.label}
            {item.source === "saved" ? <Badge tint="emerald">Saved ••••{item.last4}</Badge>
              : item.source === "server" ? <Badge tint="sky">From the server's environment ••••{item.last4}</Badge>
              : <Badge tint="slate">Not set</Badge>}</p>
          <p className="text-[13px] text-ink-3">{item.used_for}</p>
        </div>
        {!editing ? (
          <div className="flex gap-2">
            {item.source === "saved" ? <Button size="sm" variant="ghost" loading={remove.isPending} onClick={() => remove.mutate()}>Remove</Button> : null}
            <Button size="sm" onClick={() => setEditing(true)}>{item.source ? "Replace" : "Add key"}</Button>
          </div>
        ) : null}
      </div>
      {editing ? (
        <form className="mt-3 flex flex-col gap-2 sm:ml-13" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input type="password" autoComplete="off" autoFocus spellCheck={false} className="font-mono text-[13px]" aria-label={`${item.label} key`}
              placeholder={`Paste the ${item.label} key`} value={value} onChange={(e) => { setValue(e.target.value); save.reset(); }} />
            <div className="flex shrink-0 gap-2">
              <Button type="button" variant="ghost" onClick={() => { setEditing(false); setValue(""); save.reset(); }}>Cancel</Button>
              <Button type="submit" variant="primary" loading={save.isPending} disabled={value.trim().length < 16}>Check and save</Button>
            </div>
          </div>
          {save.error ? <p className="text-xs font-medium text-danger">{describeError(save.error)}</p> : null}
          <a href={item.get_key_url} target="_blank" rel="noopener noreferrer" className="inline-flex w-fit items-center gap-1 text-xs font-semibold text-jade hover:underline">
            Get a {item.label} key <ExternalLink className="size-3" />
          </a>
        </form>
      ) : null}
    </li>
  );
}

function SharedKeysTab() {
  const s = useSettings();
  if (s.error) return <Card><ErrorState message={describeError(s.error)} onRetry={() => s.refetch()} /></Card>;
  return (
    <Card className="max-w-4xl">
      <CardHeader title="Shared keys"
        subtitle="Used by every workspace that hasn't added its own key in Settings → API keys. A workspace's own key always wins." />
      <div className="mx-5 mb-4 flex items-start gap-2.5 rounded-2xl bg-glass-2 px-3.5 py-3 text-[13px] text-ink-2">
        <ShieldCheck className="mt-0.5 size-4 shrink-0 text-jade" />
        <p>Keys are checked with the provider, stored encrypted, and never shown again. Usage on a shared key counts against its free-tier limits for everyone.</p>
      </div>
      <ul className="divide-y divide-[var(--line)] border-t border-line">
        {s.data ? s.data.keys.map((k) => <SharedKeyRow key={k.provider} item={k} />)
          : [0, 1, 2, 3].map((i) => <li key={i} className="p-5"><Skeleton className="h-12" /></li>)}
      </ul>
    </Card>
  );
}

/* ================= Page ================= */

export function PlatformAdminPage() {
  const me = useAuth((s) => s.me);
  const [params, setParams] = useSearchParams();
  if (me && !me.is_platform_admin) return <Navigate to="/" replace />;
  const tabs = [
    { value: "overview", label: "Overview", content: <OverviewTab /> },
    { value: "google", label: "Google & Gmail", content: <GoogleTab /> },
    { value: "keys", label: "Shared keys", content: <SharedKeysTab /> },
  ];
  const tab = tabs.some((t) => t.value === params.get("tab")) ? params.get("tab")! : "overview";
  return (
    <>
      <PageHeader eyebrow={<span className="inline-flex items-center gap-1.5"><Check className="size-3.5" /> Platform admin</span>}
        title="Platform" description="The whole Meyora installation: every workspace, sign-in, Gmail and shared keys." />
      <Tabs.Root value={tab} onValueChange={(v) => setParams({ tab: v }, { replace: true })} className="rise flex min-h-0 flex-1 flex-col">
        <Tabs.List aria-label="Platform sections" className="glass-soft mb-3 inline-flex w-fit max-w-full flex-none gap-1 overflow-x-auto rounded-full p-1">
          {tabs.map((t) => (
            <Tabs.Trigger key={t.value} value={t.value}
              className="focus-ring flex h-8 items-center rounded-full px-3.5 text-[13px] font-semibold whitespace-nowrap text-ink-2 hover:text-ink data-[state=active]:bg-[var(--ink)] data-[state=active]:text-[var(--canvas)]">
              {t.label}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
        {tabs.map((t) => (
          <Tabs.Content key={t.value} value={t.value}
            className={cn("focus:outline-none", t.value === "overview" ? "flex min-h-0 flex-1 flex-col" : "scroll-quiet min-h-0 flex-1 overflow-y-auto pb-1")}>
            {t.content}
          </Tabs.Content>
        ))}
      </Tabs.Root>
    </>
  );
}
