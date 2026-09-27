import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import { Building2, Handshake, Magnet, UserRound } from "@/components/icons";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "@/services/api";
import { useUi } from "@/stores/ui";
import type { Company, Contact, Deal, Lead, Page } from "@/types";
import { PRIMARY_NAV, SECONDARY_NAV } from "./nav";

function useDebounced<T>(value: T, ms = 180) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Ctrl/⌘K: jump to a page, or search records across the CRM. */
export function CommandPalette() {
  const { paletteOpen: open, setPaletteOpen: setOpen } = useUi();
  const [q, setQ] = useState("");
  const term = useDebounced(q.trim());
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!useUi.getState().paletteOpen);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);

  useEffect(() => {
    if (!open) setQ("");
  }, [open]);

  const results = useQuery({
    queryKey: ["palette", term],
    enabled: open && term.length >= 2,
    queryFn: async () => {
      const params = { q: term, page_size: 5 };
      const [companies, contacts, leads, deals] = await Promise.all([
        api.get<Page<Company>>("/companies", params),
        api.get<Page<Contact>>("/contacts", params),
        api.get<Page<Lead>>("/leads", params),
        api.get<Page<Deal>>("/deals", params),
      ]);
      return { companies: companies.items, contacts: contacts.items, leads: leads.items, deals: deals.items };
    },
  });

  const go = (to: string) => {
    setOpen(false);
    navigate(to);
  };

  const item = "flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-sm data-[selected=true]:bg-glass-2";
  const group = "px-1 pt-2 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:tracking-wide [&_[cmdk-group-heading]]:text-ink-3 [&_[cmdk-group-heading]]:uppercase";
  const r = results.data;
  const hasResults = r && (r.companies.length || r.contacts.length || r.leads.length || r.deals.length);

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[rgb(14_19_17/0.25)] backdrop-blur-[2px]" />
        <Dialog.Content
          className="glass fixed top-[14vh] left-1/2 z-50 w-[min(620px,calc(100vw-24px))] -translate-x-1/2 overflow-hidden rounded-[24px] data-[state=open]:animate-[pop-in_160ms_ease-out]"
          style={{ background: "var(--glass-3)" }}
        >
          <Dialog.Title className="sr-only">Search Meyora</Dialog.Title>
          <Dialog.Description className="sr-only">Jump to a page or find a record</Dialog.Description>
          <Command shouldFilter={!term} label="Search Meyora">
            <Command.Input
              value={q}
              onValueChange={setQ}
              placeholder="Search companies, contacts, leads, deals…"
              className="h-14 w-full border-b border-line bg-transparent px-5 text-[15px] outline-none placeholder:text-ink-3"
            />
            <Command.List className="max-h-[56vh] overflow-y-auto p-2">
              {term.length >= 2 ? (
                <>
                  {results.isFetching && !r ? <Command.Loading><p className="px-3 py-6 text-center text-sm text-ink-3">Searching…</p></Command.Loading> : null}
                  {r && !hasResults ? <p className="px-3 py-8 text-center text-sm text-ink-3">No records match “{term}”.</p> : null}
                  {r?.companies.length ? (
                    <Command.Group heading="Companies" className={group}>
                      {r.companies.map((c) => (
                        <Command.Item key={c.id} value={`company-${c.id}`} onSelect={() => go(`/companies/${c.id}`)} className={item}>
                          <Building2 className="size-4 text-ink-3" /> <span className="font-medium">{c.name}</span>
                          <span className="ml-auto text-xs text-ink-3">{c.city}</span>
                        </Command.Item>
                      ))}
                    </Command.Group>
                  ) : null}
                  {r?.contacts.length ? (
                    <Command.Group heading="Contacts" className={group}>
                      {r.contacts.map((c) => (
                        <Command.Item key={c.id} value={`contact-${c.id}`} onSelect={() => go(`/contacts/${c.id}`)} className={item}>
                          <UserRound className="size-4 text-ink-3" /> <span className="font-medium">{c.full_name}</span>
                          <span className="ml-auto text-xs text-ink-3">{c.company?.name}</span>
                        </Command.Item>
                      ))}
                    </Command.Group>
                  ) : null}
                  {r?.leads.length ? (
                    <Command.Group heading="Leads" className={group}>
                      {r.leads.map((l) => (
                        <Command.Item key={l.id} value={`lead-${l.id}`} onSelect={() => go(`/leads/${l.id}`)} className={item}>
                          <Magnet className="size-4 text-ink-3" /> <span className="font-medium">{l.name}</span>
                          <span className="ml-auto text-xs text-ink-3">{l.company_name}</span>
                        </Command.Item>
                      ))}
                    </Command.Group>
                  ) : null}
                  {r?.deals.length ? (
                    <Command.Group heading="Deals" className={group}>
                      {r.deals.map((d) => (
                        <Command.Item key={d.id} value={`deal-${d.id}`} onSelect={() => go(`/deals/${d.id}`)} className={item}>
                          <Handshake className="size-4 text-ink-3" /> <span className="font-medium">{d.name}</span>
                          <span className="ml-auto text-xs text-ink-3">{d.company?.name}</span>
                        </Command.Item>
                      ))}
                    </Command.Group>
                  ) : null}
                </>
              ) : (
                <Command.Group heading="Go to" className={group}>
                  {[...PRIMARY_NAV, ...SECONDARY_NAV].map((n) => (
                    <Command.Item key={n.to} value={n.label} onSelect={() => go(n.to)} className={item}>
                      <n.icon className="size-4 text-ink-3" /> {n.label}
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
            </Command.List>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
