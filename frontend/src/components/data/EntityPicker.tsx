import * as Popover from "@radix-ui/react-popover";
import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import { Check, ChevronsUpDown, X } from "lucide-react";
import { useState } from "react";

import { useMembers } from "@/hooks/resources";
import { cn } from "@/lib/format";
import { api } from "@/services/api";
import type { Company, Contact, Deal, Lead, Page } from "@/types";

export type PickerKind = "company" | "contact" | "lead" | "deal" | "member";

const PATHS: Record<Exclude<PickerKind, "member">, string> = {
  company: "/companies",
  contact: "/contacts",
  lead: "/leads",
  deal: "/deals",
};

type Row = Company | Contact | Lead | Deal;

function rowLabel(kind: PickerKind, row: Row): string {
  if (kind === "contact") return (row as Contact).full_name;
  return (row as Company).name;
}

function useOptions(kind: PickerKind, q: string, open: boolean) {
  const members = useMembers();
  const remote = useQuery({
    queryKey: ["picker", kind, q],
    queryFn: () => api.get<Page<Row>>(PATHS[kind as keyof typeof PATHS], { q, page_size: 8 }),
    enabled: open && kind !== "member",
  });
  if (kind === "member") {
    const all = (members.data ?? []).map((m) => ({ id: m.user.id, label: m.user.full_name, sub: m.user.email }));
    const needle = q.toLowerCase();
    return { options: all.filter((o) => o.label.toLowerCase().includes(needle) || o.sub.toLowerCase().includes(needle)), loading: members.isLoading };
  }
  return {
    options: (remote.data?.items ?? []).map((r) => ({ id: r.id, label: rowLabel(kind, r), sub: "" })),
    loading: remote.isFetching,
  };
}

function useSelectedLabel(kind: PickerKind, id: string | null | undefined) {
  const members = useMembers();
  const one = useQuery({
    queryKey: [PATHS[kind as keyof typeof PATHS], "one", id],
    queryFn: () => api.get<Row>(`${PATHS[kind as keyof typeof PATHS]}/${id}`),
    enabled: Boolean(id) && kind !== "member",
    staleTime: 60_000,
  });
  if (!id) return null;
  if (kind === "member") return members.data?.find((m) => m.user.id === id)?.user.full_name ?? "…";
  return one.data ? rowLabel(kind, one.data) : "…";
}

export function EntityPicker({
  kind,
  value,
  onChange,
  placeholder,
  id,
}: {
  kind: PickerKind;
  value: string | null | undefined;
  onChange: (id: string | null) => void;
  placeholder?: string;
  id?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const { options, loading } = useOptions(kind, q, open);
  const selected = useSelectedLabel(kind, value);

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <div className="relative">
        <Popover.Trigger asChild>
          <button
            id={id}
            type="button"
            className="focus-ring glass-dense flex h-10 w-full items-center justify-between gap-2 rounded-[var(--radius-control)] px-3 text-left text-sm"
          >
            <span className={cn("truncate", !selected && "text-ink-3")}>{selected ?? placeholder ?? "Select…"}</span>
            <ChevronsUpDown className="size-4 shrink-0 text-ink-3" />
          </button>
        </Popover.Trigger>
        {value ? (
          <button
            type="button"
            aria-label="Clear"
            onClick={() => onChange(null)}
            className="focus-ring absolute top-1/2 right-8 -translate-y-1/2 rounded-full p-1 text-ink-3 hover:text-ink"
          >
            <X className="size-3.5" />
          </button>
        ) : null}
      </div>
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={6}
          className="glass z-[60] w-[var(--radix-popover-trigger-width)] min-w-64 rounded-2xl p-1.5"
          style={{ background: "var(--glass-3)" }}
        >
          <Command shouldFilter={false} label={`Search ${kind}s`}>
            <Command.Input
              autoFocus
              value={q}
              onValueChange={setQ}
              placeholder={`Search ${kind}s…`}
              className="h-9 w-full rounded-xl bg-transparent px-2.5 text-sm outline-none placeholder:text-ink-3"
            />
            <Command.List className="mt-1 max-h-64 overflow-y-auto">
              {!loading && options.length === 0 ? (
                <Command.Empty className="px-3 py-6 text-center text-sm text-ink-3">No matches</Command.Empty>
              ) : null}
              {options.map((o) => (
                <Command.Item
                  key={o.id}
                  value={o.id}
                  onSelect={() => {
                    onChange(o.id);
                    setOpen(false);
                  }}
                  className="flex cursor-pointer items-center gap-2 rounded-xl px-2.5 py-2 text-sm data-[selected=true]:bg-glass-2"
                >
                  <Check className={cn("size-4 text-jade", o.id === value ? "opacity-100" : "opacity-0")} />
                  <span className="truncate font-medium">{o.label}</span>
                  {o.sub ? <span className="truncate text-xs text-ink-3">{o.sub}</span> : null}
                </Command.Item>
              ))}
            </Command.List>
          </Command>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

/** Read-only name for a linked record, e.g. in tables and detail headers. */
export function EntityName({ kind, id }: { kind: PickerKind; id: string | null | undefined }) {
  const label = useSelectedLabel(kind, id);
  return <>{label ?? "—"}</>;
}
