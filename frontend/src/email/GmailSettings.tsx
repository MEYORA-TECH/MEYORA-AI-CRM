import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Mail, RefreshCw, Unplug } from "@/components/icons";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/ui/overlay";
import { Badge, Button, Card, CardHeader, EmptyState, Skeleton } from "@/components/ui/primitives";
import { relative } from "@/lib/format";
import { api, describeError } from "@/services/api";
import { useAuth, useCan } from "@/stores/auth";
import { useGmail, type MailAccount } from "./api";

const RETURN_MESSAGES: Record<string, [string, "success" | "error"]> = {
  connected: ["Gmail connected. The first sync is running.", "success"],
  cancelled: ["Gmail connection was cancelled.", "error"],
  failed: ["Couldn't connect Gmail. Allow read access to your mail and try again.", "error"],
  taken: ["That mailbox is already connected by a teammate.", "error"],
  disabled: ["Gmail sync is turned off. A platform admin can turn it on in Platform → Google & Gmail.", "error"],
};

const STATUS: Record<string, { label: string; tint: "emerald" | "amber" | "slate" }> = {
  connected: { label: "Connected", tint: "emerald" },
  reconnect_required: { label: "Needs reconnecting", tint: "amber" },
  disconnected: { label: "Disconnected", tint: "slate" },
};

export function GmailSettings() {
  const qc = useQueryClient();
  const me = useAuth((s) => s.me);
  const isPlatformAdmin = Boolean(me?.is_platform_admin);
  const canWrite = useCan("crm:write");
  const gmail = useGmail();
  const [params, setParams] = useSearchParams();
  const [disconnecting, setDisconnecting] = useState<MailAccount | null>(null);

  useEffect(() => {
    const result = params.get("gmail");
    if (!result) return;
    const [message, kind] = RETURN_MESSAGES[result] ?? ["Gmail connection finished.", "success"];
    (kind === "success" ? toast.success : toast.error)(message);
    params.delete("gmail");
    setParams(params, { replace: true });
    qc.invalidateQueries({ queryKey: ["gmail"] });
  }, [params, setParams, qc]);

  const connect = useMutation({
    mutationFn: () => api.post<{ url: string }>("/integrations/gmail/connect"),
    onSuccess: ({ url }) => window.location.assign(url),
    onError: (e) => toast.error(describeError(e)),
  });
  const syncNow = useMutation({
    mutationFn: (id: string) => api.post(`/integrations/gmail/${id}/sync`),
    onSuccess: () => {
      toast.success("Sync started");
      setTimeout(() => qc.invalidateQueries({ queryKey: ["gmail"] }), 4000);
    },
    onError: (e) => toast.error(describeError(e)),
  });
  const disconnect = useMutation({
    mutationFn: (id: string) => api.delete(`/integrations/gmail/${id}`),
    onSuccess: () => {
      setDisconnecting(null);
      qc.invalidateQueries({ queryKey: ["gmail"] });
      toast.success("Gmail disconnected");
    },
    onError: (e) => toast.error(describeError(e)),
  });

  if (gmail.isLoading) return <Skeleton className="h-48" />;
  const accounts = gmail.data?.accounts ?? [];
  const mine = accounts.find((a) => a.user_id === me?.id && a.status !== "disconnected");

  return (
    <Card>
      <CardHeader
        title="Email"
        subtitle="Only emails with your CRM contacts and companies are stored. Everyone in the workspace can see them."
        action={gmail.data?.enabled && canWrite && !mine ? (
          <Button size="sm" variant="primary" icon={<Mail className="size-4" />} loading={connect.isPending} onClick={() => connect.mutate()}>
            Connect Gmail
          </Button>
        ) : null}
      />
      {!gmail.data?.enabled ? (
        <EmptyState icon={<Mail className="size-5" />} title="Gmail sync is turned off"
          body={isPlatformAdmin
            ? "Add a Google OAuth client and turn Gmail sync on for this installation."
            : "A platform admin can turn it on for this installation."}
          action={isPlatformAdmin ? <Link to="/admin?tab=google"><Button size="sm">Open Platform → Google &amp; Gmail</Button></Link> : undefined} />
      ) : accounts.length === 0 ? (
        <EmptyState icon={<Mail className="size-5" />} title="No mailboxes connected"
          body="Connect Gmail to see conversations on contact and company pages and let the assistant use them." />
      ) : (
        <ul className="divide-y divide-[var(--line)]">
          {accounts.map((a) => {
            const status = STATUS[a.status] ?? { label: a.status, tint: "slate" as const };
            const own = a.user_id === me?.id;
            return (
              <li key={a.id} className="flex flex-wrap items-center gap-3 px-5 py-3.5">
                <span className="flex size-9 items-center justify-center rounded-xl bg-tint-sky"><Mail className="size-4" /></span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold">{a.email_address}</p>
                  <p className="text-xs text-ink-3">
                    {a.messages_synced} email{a.messages_synced === 1 ? "" : "s"} stored
                    {a.last_sync_at ? ` · synced ${relative(a.last_sync_at)}` : " · first sync pending"}
                  </p>
                  {a.last_error ? <p className="mt-0.5 text-xs font-medium text-warn">{a.last_error}</p> : null}
                </div>
                <Badge tint={status.tint}>{status.label}</Badge>
                {own && canWrite ? (
                  a.status === "connected" ? (
                    <>
                      <Button size="sm" icon={<RefreshCw className="size-4" />} loading={syncNow.isPending} onClick={() => syncNow.mutate(a.id)}>Sync now</Button>
                      <Button size="sm" variant="ghost" icon={<Unplug className="size-4" />} onClick={() => setDisconnecting(a)}>Disconnect</Button>
                    </>
                  ) : (
                    <Button size="sm" variant="primary" loading={connect.isPending} onClick={() => connect.mutate()}>Reconnect</Button>
                  )
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
      <ConfirmDialog
        open={Boolean(disconnecting)}
        onOpenChange={(o) => !o && setDisconnecting(null)}
        title="Disconnect Gmail?"
        description="Meyora stops syncing and removes its access at Google. Emails already stored stay in the CRM."
        confirmLabel="Disconnect"
        loading={disconnect.isPending}
        onConfirm={() => disconnecting && disconnect.mutate(disconnecting.id)}
      />
    </Card>
  );
}
