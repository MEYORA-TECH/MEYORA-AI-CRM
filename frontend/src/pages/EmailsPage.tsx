import { Mail, Search } from "@/components/icons";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useGmail, useThreads } from "@/email/api";
import { ThreadList, ThreadView } from "@/email/components";
import { Button, Card, EmptyState, ErrorState, Input, Skeleton } from "@/components/ui/primitives";
import { PageHeader } from "@/layouts/AppShell";
import { relative } from "@/lib/format";
import { describeError } from "@/services/api";

export function EmailsPage() {
  const { id } = useParams();
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setQ(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);
  const list = useThreads({ q: q || undefined });
  const gmail = useGmail();
  const connected = gmail.data?.accounts.filter((a) => a.status === "connected") ?? [];
  const lastSync = connected.map((a) => a.last_sync_at).filter(Boolean).sort().at(-1);

  return (
    <>
      <PageHeader
        title="Emails"
        description={
          connected.length
            ? `Conversations with your contacts and companies, from ${connected.length} connected mailbox${connected.length === 1 ? "" : "es"}${lastSync ? ` · synced ${relative(lastSync)}` : ""}.`
            : "Conversations with your contacts and companies, synced from Gmail."
        }
        actions={<Link to="/settings?tab=email"><Button>Mailbox settings</Button></Link>}
      />
      <div className="rise grid min-h-0 flex-1 gap-4 lg:grid-cols-[380px_minmax(0,1fr)]">
        <Card className="flex min-h-0 flex-col">
          <div className="p-3">
            <div className="relative">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" />
              <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search subject, text or sender" aria-label="Search emails" className="pl-9" />
            </div>
          </div>
          <div className="scroll-quiet min-h-0 flex-1 overflow-y-auto">
            {list.isLoading ? (
              <div className="space-y-3 p-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}</div>
            ) : list.error ? (
              <ErrorState message={describeError(list.error)} onRetry={() => list.refetch()} />
            ) : list.data?.items.length ? (
              <ThreadList threads={list.data.items} activeId={id} />
            ) : (
              <EmptyState
                icon={<Mail className="size-5" />}
                title={q ? "No matching emails" : "No emails yet"}
                body={q ? "Try other words." : gmail.data?.enabled
                  ? "Connect Gmail in Settings. Only emails with your CRM contacts and companies are stored."
                  : "Gmail sync is turned off on this server."}
              />
            )}
          </div>
        </Card>
        <Card className="scroll-quiet hidden min-h-0 overflow-y-auto lg:block">
          {id ? <ThreadView id={id} /> : <EmptyState title="Pick a conversation" body="Select a thread to read it, summarise it, or draft a reply with the assistant." className="h-full" />}
        </Card>
      </div>
      {id ? <Card className="mt-4 lg:hidden"><ThreadView id={id} /></Card> : null}
    </>
  );
}
