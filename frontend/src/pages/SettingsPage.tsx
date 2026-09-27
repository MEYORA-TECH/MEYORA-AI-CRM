import * as Tabs from "@radix-ui/react-tabs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Copy, Plus, Trash2, UserMinus } from "@/components/icons";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { GmailSettings } from "@/email/GmailSettings";
import { ApiKeysTab } from "@/settings/ApiKeysTab";
import { toast } from "sonner";

import { ConfirmDialog, Modal } from "@/components/ui/overlay";
import { Avatar, Badge, Button, Card, CardHeader, EmptyState, ErrorState, Field, IconButton, Input, Select, Skeleton, tintBg } from "@/components/ui/primitives";
import { useMembers, usePipelines } from "@/hooks/resources";
import { PageHeader } from "@/layouts/AppShell";
import { cn, dateTime, label, relative } from "@/lib/format";
import { api, describeError } from "@/services/api";
import { useAuth, useCan } from "@/stores/auth";
import type { AuditLog, Invitation, InvitationCreated, Organization, Page, Pipeline, Role } from "@/types";

const ROLES: { value: Role; label: string; hint: string }[] = [
  { value: "member", label: "Member", hint: "Views and edits all CRM records" },
  { value: "manager", label: "Manager", hint: "Also deletes records and manages pipelines" },
  { value: "admin", label: "Admin", hint: "Also manages members and organization settings" },
  { value: "owner", label: "Owner", hint: "Full control, including ownership" },
];

/* ---------------- Organization ---------------- */

function OrganizationTab() {
  const qc = useQueryClient();
  const canManage = useCan("org:manage");
  const org = useQuery({ queryKey: ["/organization"], queryFn: () => api.get<Organization>("/organization") });
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("INR");
  useEffect(() => {
    if (org.data) {
      setName(org.data.name);
      setCurrency(org.data.default_currency);
    }
  }, [org.data]);
  const save = useMutation({
    mutationFn: () => api.patch<Organization>("/organization", { name, default_currency: currency }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["/organization"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Organization saved");
    },
    onError: (e) => toast.error(describeError(e)),
  });

  if (org.error) return <ErrorState message={describeError(org.error)} onRetry={() => org.refetch()} />;
  return (
    <Card>
      <CardHeader title="Organization" subtitle={canManage ? "Shown to everyone in your workspace." : "Only admins can change these settings."} />
      <form className="grid max-w-xl gap-4 px-5 pb-5 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <Field label="Name" htmlFor="org-name" className="sm:col-span-2">
          <Input id="org-name" value={name} disabled={!canManage} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Default currency" htmlFor="org-currency" hint="Dashboard totals use this currency.">
          <Select id="org-currency" value={currency} disabled={!canManage} onChange={(e) => setCurrency(e.target.value)}>
            {["INR", "USD", "EUR", "GBP", "AED", "SGD"].map((c) => <option key={c}>{c}</option>)}
          </Select>
        </Field>
        {canManage ? <div className="flex items-end sm:col-span-2"><Button variant="primary" type="submit" loading={save.isPending}>Save changes</Button></div> : null}
      </form>
    </Card>
  );
}

/* ---------------- Members ---------------- */

function MembersTab() {
  const qc = useQueryClient();
  const me = useAuth((s) => s.me);
  const canManage = useCan("members:manage");
  const members = useMembers();
  const invitations = useQuery({
    queryKey: ["/organization/invitations"],
    queryFn: () => api.get<Invitation[]>("/organization/invitations"),
    enabled: canManage,
  });
  const [inviting, setInviting] = useState(false);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [link, setLink] = useState<string | null>(null);
  const [removing, setRemoving] = useState<{ id: string; name: string } | null>(null);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["/organization/members"] });
    qc.invalidateQueries({ queryKey: ["/organization/invitations"] });
  };
  const invite = useMutation({
    mutationFn: () => api.post<InvitationCreated>("/organization/invitations", { email, role }),
    onSuccess: (inv) => {
      setLink(`${window.location.origin}/register?invite=${encodeURIComponent(inv.token)}&email=${encodeURIComponent(inv.email)}`);
      refresh();
    },
    onError: (e) => toast.error(describeError(e)),
  });
  const changeRole = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: Role }) => api.patch(`/organization/members/${userId}`, { role }),
    onSuccess: () => { refresh(); toast.success("Role updated"); },
    onError: (e) => toast.error(describeError(e)),
  });
  const remove = useMutation({
    mutationFn: (userId: string) => api.delete(`/organization/members/${userId}`),
    onSuccess: () => { refresh(); setRemoving(null); toast.success("Member removed"); },
    onError: (e) => toast.error(describeError(e)),
  });
  const revoke = useMutation({
    mutationFn: (id: string) => api.delete(`/organization/invitations/${id}`),
    onSuccess: () => { refresh(); toast.success("Invitation revoked"); },
    onError: (e) => toast.error(describeError(e)),
  });

  const closeInvite = (open: boolean) => {
    setInviting(open);
    if (!open) { setLink(null); setEmail(""); setRole("member"); }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Members"
          subtitle={`${members.data?.length ?? 0} people in this workspace`}
          action={canManage ? <Button size="sm" variant="primary" icon={<Plus className="size-4" />} onClick={() => setInviting(true)}>Invite</Button> : null}
        />
        {members.isLoading ? <div className="space-y-3 p-5"><Skeleton className="h-10" /><Skeleton className="h-10" /></div> : (
          <ul className="divide-y divide-[var(--line)]">
            {members.data?.map((m) => {
              const self = m.user.id === me?.id;
              return (
                <li key={m.user.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
                  <Avatar name={m.user.full_name} size={34} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold">{m.user.full_name}{self ? <span className="font-normal text-ink-3"> (you)</span> : null}</p>
                    <p className="truncate text-xs text-ink-3">{m.user.email} · joined {relative(m.created_at)}</p>
                  </div>
                  {canManage && !self ? (
                    <>
                      <Select aria-label={`Role for ${m.user.full_name}`} value={m.role} className="h-9 w-auto"
                        onChange={(e) => changeRole.mutate({ userId: m.user.id, role: e.target.value as Role })}>
                        {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                      </Select>
                      <IconButton label={`Remove ${m.user.full_name}`} onClick={() => setRemoving({ id: m.user.id, name: m.user.full_name })}>
                        <UserMinus className="size-4" />
                      </IconButton>
                    </>
                  ) : (
                    <Badge tint={m.role === "owner" ? "jade" : "slate"}>{label(m.role)}</Badge>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      {canManage ? (
        <Card>
          <CardHeader title="Pending invitations" subtitle="Links expire after 7 days." />
          {invitations.data?.length ? (
            <ul className="divide-y divide-[var(--line)]">
              {invitations.data.map((i) => (
                <li key={i.id} className="flex items-center gap-3 px-5 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold">{i.email}</p>
                    <p className="text-xs text-ink-3">{label(i.role)} · expires {relative(i.expires_at)}</p>
                  </div>
                  <Button size="sm" variant="ghost" onClick={() => revoke.mutate(i.id)}>Revoke</Button>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No pending invitations" body="Invite teammates to share leads, deals and history." />
          )}
        </Card>
      ) : null}

      <Modal
        open={inviting}
        onOpenChange={closeInvite}
        title={link ? "Share the invitation link" : "Invite a teammate"}
        description={link ? "Email isn't connected yet, so send this link yourself. It works once, for this address only." : undefined}
        footer={link ? <Button variant="primary" onClick={() => closeInvite(false)}>Done</Button> : (
          <>
            <Button variant="ghost" onClick={() => closeInvite(false)}>Cancel</Button>
            <Button variant="primary" loading={invite.isPending} disabled={!email} onClick={() => invite.mutate()}>Create invitation</Button>
          </>
        )}
      >
        {link ? (
          <div className="flex gap-2">
            <Input readOnly value={link} aria-label="Invitation link" onFocus={(e) => e.target.select()} />
            <Button icon={<Copy className="size-4" />} onClick={async () => {
              try { await navigator.clipboard.writeText(link); toast.success("Link copied"); } catch { toast.error("Copy failed. Select the link and copy it."); }
            }}>Copy</Button>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <Field label="Email" htmlFor="invite-email">
              <Input id="invite-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
            </Field>
            <Field label="Role" htmlFor="invite-role" hint={ROLES.find((r) => r.value === role)?.hint}>
              <Select id="invite-role" value={role} onChange={(e) => setRole(e.target.value as Role)}>
                {ROLES.filter((r) => r.value !== "owner" || me?.role === "owner").map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
              </Select>
            </Field>
          </div>
        )}
      </Modal>
      <ConfirmDialog
        open={Boolean(removing)}
        onOpenChange={(o) => !o && setRemoving(null)}
        title={`Remove ${removing?.name}?`}
        description="They lose access immediately. Records they own stay in the workspace."
        confirmLabel="Remove member"
        loading={remove.isPending}
        onConfirm={() => removing && remove.mutate(removing.id)}
      />
    </div>
  );
}

/* ---------------- Pipelines ---------------- */

type StageDraft = { id?: string; name: string; probability: number; kind: "open" | "won" | "lost"; color: string };
const COLORS = ["slate", "sky", "violet", "amber", "orange", "emerald", "rose"];

function PipelineEditor({ pipeline }: { pipeline: Pipeline }) {
  const qc = useQueryClient();
  const canManage = useCan("pipelines:manage");
  const [stages, setStages] = useState<StageDraft[]>([]);
  useEffect(() => {
    setStages(pipeline.stages.map(({ id, name, probability, kind, color }) => ({ id, name, probability, kind, color })));
  }, [pipeline]);

  const save = useMutation({
    mutationFn: () => api.patch<Pipeline>(`/pipelines/${pipeline.id}`, { stages }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["/pipelines"] });
      qc.invalidateQueries({ queryKey: ["/deals"] });
      toast.success("Pipeline saved");
    },
    onError: (e) => toast.error(describeError(e)),
  });

  const patch = (i: number, p: Partial<StageDraft>) => setStages((s) => s.map((x, j) => (j === i ? { ...x, ...p } : x)));
  const move = (i: number, d: -1 | 1) => setStages((s) => {
    const next = [...s];
    [next[i], next[i + d]] = [next[i + d], next[i]];
    return next;
  });

  return (
    <Card>
      <CardHeader title={pipeline.name} subtitle="Stages in order. A pipeline needs at least one open stage, one won and one lost." />
      <ul className="space-y-2 px-5">
        {stages.map((s, i) => (
          <li key={s.id ?? `new-${i}`} className="glass-dense grid grid-cols-[auto_1fr] items-center gap-2 rounded-2xl p-2 sm:grid-cols-[auto_1fr_88px_110px_110px_auto]">
            <span className={cn("size-3 rounded-full", tintBg(s.color))} style={{ boxShadow: "inset 0 0 0 1px var(--line-strong)" }} />
            <Input aria-label="Stage name" value={s.name} disabled={!canManage} onChange={(e) => patch(i, { name: e.target.value })} className="h-9" />
            <Input aria-label="Probability" type="number" min={0} max={100} value={s.probability} disabled={!canManage} className="num h-9"
              onChange={(e) => patch(i, { probability: Math.max(0, Math.min(100, Number(e.target.value))) })} />
            <Select aria-label="Kind" value={s.kind} disabled={!canManage} className="h-9" onChange={(e) => patch(i, { kind: e.target.value as StageDraft["kind"] })}>
              <option value="open">Open</option><option value="won">Won</option><option value="lost">Lost</option>
            </Select>
            <Select aria-label="Colour" value={s.color} disabled={!canManage} className="h-9" onChange={(e) => patch(i, { color: e.target.value })}>
              {COLORS.map((c) => <option key={c} value={c}>{label(c)}</option>)}
            </Select>
            {canManage ? (
              <div className="flex">
                <IconButton label="Move up" disabled={i === 0} onClick={() => move(i, -1)} className="size-8 disabled:opacity-30"><ArrowUp className="size-4" /></IconButton>
                <IconButton label="Move down" disabled={i === stages.length - 1} onClick={() => move(i, 1)} className="size-8 disabled:opacity-30"><ArrowDown className="size-4" /></IconButton>
                <IconButton label="Remove stage" onClick={() => setStages((x) => x.filter((_, j) => j !== i))} className="size-8"><Trash2 className="size-4" /></IconButton>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
      {canManage ? (
        <div className="flex justify-between gap-2 p-5">
          <Button size="sm" icon={<Plus className="size-4" />} onClick={() => setStages((s) => [...s, { name: "New stage", probability: 50, kind: "open", color: "sky" }])}>Add stage</Button>
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>Save pipeline</Button>
        </div>
      ) : <div className="p-3" />}
    </Card>
  );
}

function PipelinesTab() {
  const pipelines = usePipelines();
  if (pipelines.error) return <ErrorState message={describeError(pipelines.error)} onRetry={() => pipelines.refetch()} />;
  if (!pipelines.data) return <Skeleton className="h-80" />;
  return <div className="space-y-4">{pipelines.data.map((p) => <PipelineEditor key={p.id} pipeline={p} />)}</div>;
}

/* ---------------- Audit log ---------------- */

function AuditTab() {
  const [page, setPage] = useState(1);
  const members = useMembers();
  const logs = useQuery({
    queryKey: ["/organization/audit-logs", page],
    queryFn: () => api.get<Page<AuditLog>>("/organization/audit-logs", { page, page_size: 30 }),
  });
  const who = (id: string | null) => members.data?.find((m) => m.user.id === id)?.user.full_name ?? "System";
  if (logs.error) return <ErrorState message={describeError(logs.error)} onRetry={() => logs.refetch()} />;
  return (
    <Card>
      <CardHeader title="Audit log" subtitle="Every change, sign-in and permission update in this workspace." />
      {!logs.data ? <div className="space-y-2 p-5"><Skeleton className="h-8" /><Skeleton className="h-8" /></div> : logs.data.items.length === 0 ? (
        <EmptyState title="No events yet" />
      ) : (
        <ul className="divide-y divide-[var(--line)]">
          {logs.data.items.map((l) => (
            <li key={l.id} className="grid gap-1 px-5 py-2.5 sm:grid-cols-[150px_1fr_auto] sm:items-center sm:gap-4">
              <span className="font-mono text-xs text-ink-3">{dateTime(l.created_at)}</span>
              <span className="min-w-0 text-sm">
                <span className="font-semibold">{who(l.actor_user_id)}</span>{" "}
                <span className="font-mono text-[12px] text-ink-2">{l.action}</span>
                {Object.keys(l.changes).length ? (
                  <span className="block truncate text-xs text-ink-3">
                    {Object.entries(l.changes).map(([k, v]) => `${k}: ${fmt((v as { old: unknown }).old)} → ${fmt((v as { new: unknown }).new)}`).join(" · ")}
                  </span>
                ) : null}
              </span>
              {l.actor_type !== "user" ? <Badge tint="violet">{label(l.actor_type)}</Badge> : <span />}
            </li>
          ))}
        </ul>
      )}
      {logs.data && logs.data.total > 30 ? (
        <div className="flex justify-end gap-2 p-4">
          <Button size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Newer</Button>
          <Button size="sm" disabled={page * 30 >= logs.data.total} onClick={() => setPage(page + 1)}>Older</Button>
        </div>
      ) : null}
    </Card>
  );
}

const fmt = (v: unknown) => (v === null || v === undefined || v === "" ? "∅" : Array.isArray(v) ? v.join(", ") : String(v));

/* ---------------- Page ---------------- */

export function SettingsPage() {
  const canAudit = useCan("audit:read");
  const canManageKeys = useCan("org:secrets");
  const [params, setParams] = useSearchParams();
  const tabs = [
    { value: "organization", label: "Organization", content: <OrganizationTab /> },
    { value: "members", label: "Members", content: <MembersTab /> },
    { value: "pipelines", label: "Pipelines", content: <PipelinesTab /> },
    { value: "email", label: "Email", content: <GmailSettings /> },
    ...(canManageKeys ? [{ value: "api-keys", label: "API keys", content: <ApiKeysTab /> }] : []),
    ...(canAudit ? [{ value: "audit", label: "Audit log", content: <AuditTab /> }] : []),
  ];
  const tab = tabs.some((t) => t.value === params.get("tab")) ? params.get("tab")! : "organization";
  return (
    <>
      <PageHeader title="Settings" description="Workspace, people, pipelines, email, API keys and history." />
      <Tabs.Root value={tab} onValueChange={(v) => setParams({ tab: v }, { replace: true })} className="rise flex min-h-0 flex-1 flex-col">
        <Tabs.List aria-label="Settings sections" className="glass-soft mb-4 inline-flex w-fit max-w-full flex-none gap-1 overflow-x-auto rounded-full p-1">
          {tabs.map((t) => (
            <Tabs.Trigger key={t.value} value={t.value}
              className="focus-ring flex h-8 items-center gap-1.5 rounded-full px-3.5 text-[13px] font-semibold whitespace-nowrap text-ink-2 hover:text-ink data-[state=active]:bg-[var(--ink)] data-[state=active]:text-[var(--canvas)]">
              {t.label}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
        {tabs.map((t) => (
          <Tabs.Content key={t.value} value={t.value} className="scroll-quiet min-h-0 max-w-4xl flex-1 overflow-y-auto pb-1 focus:outline-none">
            {t.content}
          </Tabs.Content>
        ))}
      </Tabs.Root>
    </>
  );
}
