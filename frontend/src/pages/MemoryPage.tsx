import { Brain, Search } from "@/components/icons";
import { useEffect, useState } from "react";

import { AddMemoryButton, MemoryList, useMemories } from "@/ai/memories";
import { Card, EmptyState, Input, Select } from "@/components/ui/primitives";
import { PageHeader } from "@/layouts/AppShell";
import { cn } from "@/lib/format";

const VIEWS = [
  { value: "", label: "Active" },
  { value: "pending_review", label: "Needs review" },
  { value: "superseded", label: "Replaced" },
];

export function MemoryPage() {
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [scope, setScope] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setQ(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  const list = useMemories({ q: q || undefined, status: status || undefined, scope: scope || undefined });
  const pending = useMemories({ status: "pending_review" });

  return (
    <>
      <PageHeader
        title="Memory"
        description="Facts the assistant has learned about your customers and team, and where each came from."
        actions={<AddMemoryButton size="md" />}
      />
      <div className="rise mb-3 flex flex-none flex-wrap items-center gap-2">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by meaning, e.g. deployment preferences"
            aria-label="Search memories" className="pl-9" />
        </div>
        <div className="glass-soft flex gap-1 rounded-full p-1" role="group" aria-label="Status">
          {VIEWS.map((v) => (
            <button key={v.value} onClick={() => setStatus(v.value)} aria-pressed={status === v.value}
              className={cn("focus-ring flex h-8 items-center gap-1.5 rounded-full px-3.5 text-[13px] font-semibold text-ink-2", status === v.value && "bg-[var(--ink)] text-[var(--canvas)]")}>
              {v.label}
              {v.value === "pending_review" && pending.data?.total ? <span className="num text-[11px] opacity-70">{pending.data.total}</span> : null}
            </button>
          ))}
        </div>
        <Select aria-label="Scope" value={scope} onChange={(e) => setScope(e.target.value)} className="w-auto">
          <option value="">About: anything</option>
          <option value="organization">The whole business</option>
          <option value="company">Companies</option>
          <option value="contact">Contacts</option>
          <option value="deal">Deals</option>
          <option value="user">Only me</option>
        </Select>
      </div>
      <Card className="rise scroll-quiet min-h-0 flex-1 overflow-y-auto">
        <MemoryList
          items={list.data?.items}
          loading={list.isLoading}
          empty={
            <EmptyState icon={<Brain className="size-5" />}
              title={q || status || scope ? "No matching memories" : "No memories yet"}
              body={q || status || scope ? "Try other words or filters." : "Tell the assistant “remember that…”, write notes on records, or add a memory here."} />
          }
        />
      </Card>
    </>
  );
}
