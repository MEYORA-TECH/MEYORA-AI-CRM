import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { useAiUi } from "@/ai/store";
import { ExternalLink, Linkedin, Search } from "@/components/icons";
import { Button, Input } from "@/components/ui/primitives";
import { api, describeError } from "@/services/api";
import { useCan } from "@/stores/auth";

interface Candidate {
  url: string;
  title: string;
  snippet: string;
}

const short = (url: string) => url.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");

/**
 * A record's LinkedIn page: open it, find it (public pages only, via web search), or draft
 * outreach with the assistant. Meyora never sends on LinkedIn; people send drafts themselves.
 */
export function LinkedInBox({ entity, id, url, name, onSave, person }: {
  entity: "companies" | "contacts" | "leads";
  id: string;
  url: string | null;
  name: string;
  onSave: (url: string | null) => Promise<unknown>;
  /** Contacts and people-leads can get a drafted connection note or message. */
  person?: boolean;
}) {
  const canWrite = useCan("crm:write");
  const ask = useAiUi((s) => s.ask);
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [pasting, setPasting] = useState(false);
  const [pasted, setPasted] = useState("");

  const find = useMutation({
    mutationFn: () => api.get<{ candidates: Candidate[] }>(`/linkedin/lookup/${entity}/${id}`),
    onSuccess: (r) => setCandidates(r.candidates),
    onError: (e) => toast.error(describeError(e)),
  });
  const save = useMutation({
    mutationFn: (value: string | null) => onSave(value),
    onSuccess: (_d, value) => {
      setCandidates(null);
      setPasting(false);
      setPasted("");
      toast.success(value ? "LinkedIn page saved" : "LinkedIn page removed");
    },
    onError: (e) => toast.error(describeError(e)),
  });

  const draft = (kind: "note" | "message") =>
    ask(kind === "note"
      ? `Draft a LinkedIn connection note to ${name}: under 300 characters, personal, and why we're reaching out.`
      : `Draft a LinkedIn message to ${name} about how we could help them. Keep it short and specific.`);

  return (
    <div className="mt-4 border-t border-line pt-4">
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-[13px] font-semibold"><Linkedin className="size-4 text-[#0a66c2]" /> LinkedIn</p>
        {url && canWrite ? (
          <button type="button" className="text-xs font-semibold text-ink-3 hover:text-ink" onClick={() => { setPasting(true); setPasted(url); }}>
            Change
          </button>
        ) : null}
      </div>

      {url && !pasting ? (
        <a href={url} target="_blank" rel="noopener noreferrer" className="mt-1.5 inline-flex max-w-full items-center gap-1 truncate text-sm font-medium text-jade hover:underline">
          <span className="truncate">{short(url)}</span> <ExternalLink className="size-3 shrink-0" />
        </a>
      ) : null}

      {!url && !candidates && !pasting ? (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {canWrite ? (
            <>
              <Button size="sm" icon={<Search className="size-3.5" />} loading={find.isPending} onClick={() => find.mutate()}>
                Find on LinkedIn
              </Button>
              <button type="button" className="text-xs font-semibold text-ink-3 hover:text-ink" onClick={() => setPasting(true)}>Paste a link</button>
            </>
          ) : <p className="text-xs text-ink-3">Not linked yet.</p>}
        </div>
      ) : null}

      {candidates ? (
        <div className="mt-2 space-y-1.5">
          {candidates.length ? candidates.map((c) => (
            <div key={c.url} className="glass-dense flex items-start gap-2 rounded-xl p-2.5">
              <div className="min-w-0 flex-1">
                <a href={c.url} target="_blank" rel="noopener noreferrer" className="block truncate text-[13px] font-semibold hover:underline">{c.title}</a>
                <p className="truncate text-[11px] text-ink-3">{short(c.url)}</p>
                {c.snippet ? <p className="mt-0.5 line-clamp-2 text-[11px] text-ink-2">{c.snippet}</p> : null}
              </div>
              <Button size="sm" variant="primary" loading={save.isPending && save.variables === c.url} onClick={() => save.mutate(c.url)}>Use</Button>
            </div>
          )) : <p className="text-xs text-ink-3">No public LinkedIn page found for {name}.</p>}
          <div className="flex gap-3 pt-0.5 text-xs font-semibold">
            <button type="button" className="text-ink-3 hover:text-ink" onClick={() => { setCandidates(null); setPasting(true); }}>Paste a link instead</button>
            <button type="button" className="text-ink-3 hover:text-ink" onClick={() => setCandidates(null)}>Close</button>
          </div>
          <p className="text-[11px] text-ink-3">Found with a public web search (one search credit). Check it's the right one before using it.</p>
        </div>
      ) : null}

      {pasting ? (
        <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); save.mutate(pasted.trim() || null); }}>
          <Input autoFocus value={pasted} onChange={(e) => setPasted(e.target.value)} className="h-8 text-[13px]"
            placeholder={person ? "https://www.linkedin.com/in/…" : "https://www.linkedin.com/company/…"} aria-label="LinkedIn link" />
          <Button size="sm" variant="primary" type="submit" loading={save.isPending}>{pasted.trim() ? "Save" : "Remove"}</Button>
          <Button size="sm" variant="ghost" type="button" onClick={() => { setPasting(false); setPasted(""); }}>Cancel</Button>
        </form>
      ) : null}

      {person && canWrite ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" variant="ghost" onClick={() => draft("note")}>Draft connection note</Button>
          <Button size="sm" variant="ghost" onClick={() => draft("message")}>Draft message</Button>
        </div>
      ) : null}
    </div>
  );
}
