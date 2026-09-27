import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Globe, NotebookPen, RefreshCw } from "@/components/icons";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";

import { Badge, Button, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { relative } from "@/lib/format";
import { api, describeError } from "@/services/api";
import { useCan } from "@/stores/auth";
import type { components } from "@/types/api";

type Brief = components["schemas"]["BriefOut"];
type WebStatus = components["schemas"]["WebStatus"];
type Source = { n: number; title: string; url: string; domain: string; published?: string | null };

export function useWebStatus() {
  return useQuery({ queryKey: ["web", "status"], queryFn: () => api.get<WebStatus>("/web/status"), staleTime: 60_000 });
}

/** Turn [2] citations into links to the matching source. */
function linkCitations(text: string, sources: Source[]) {
  return text.replace(/\[(\d{1,2})\]/g, (m, n) => {
    const s = sources.find((x) => x.n === Number(n));
    return s ? `[[${n}]](${s.url})` : m;
  });
}

export function WebResearchPanel({ kind, id }: { kind: "companies" | "leads"; id: string }) {
  const qc = useQueryClient();
  const canWrite = useCan("crm:write");
  const status = useWebStatus();
  const briefs = useQuery({ queryKey: ["research", kind, id], queryFn: () => api.get<Brief[]>(`/research/${kind}/${id}`) });
  const research = useMutation({
    mutationFn: () => api.post<Brief>(`/research/${kind}/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["research", kind, id] });
      qc.invalidateQueries({ queryKey: ["web", "status"] });
    },
    onError: (e) => toast.error(describeError(e)),
  });
  const saveNote = useMutation({
    mutationFn: (briefId: string) => api.post(`/research/briefs/${briefId}/save-note`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["/notes"] });
      qc.invalidateQueries({ queryKey: ["timeline"] });
      toast.success("Saved as a note");
    },
    onError: (e) => toast.error(describeError(e)),
  });

  const latest = briefs.data?.[0];
  const sources = (latest?.sources ?? []) as unknown as Source[];
  const enabled = status.data?.enabled;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
        <p className="flex items-center gap-2 text-xs text-ink-3">
          <Badge tint="amber" className="h-5 px-2 text-[10px]"><Globe className="size-3" /> Web</Badge>
          From public websites and news. Not verified, and never copied into the CRM unless you save it.
        </p>
        {canWrite && enabled ? (
          <Button size="sm" variant={latest ? "secondary" : "primary"} icon={<RefreshCw className="size-4" />} loading={research.isPending}
            onClick={() => research.mutate()}>
            {latest ? "Research again" : "Research now"}
          </Button>
        ) : null}
      </div>

      {briefs.isLoading || research.isPending ? (
        <div className="space-y-3 p-5">
          {research.isPending ? <p className="text-sm text-ink-3">Searching the web and writing a brief…</p> : null}
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-10" />)}
        </div>
      ) : briefs.error ? (
        <ErrorState message={describeError(briefs.error)} onRetry={() => briefs.refetch()} />
      ) : !latest ? (
        <EmptyState icon={<Globe className="size-5" />} title="No web research yet"
          body={enabled ? "Get a short, cited brief on what they do, recent news and buying signals." : "Web research is off. An admin can add a TAVILY_API_KEY to turn it on."} />
      ) : (
        <div className="px-5 py-4">
          <p className="mb-3 text-xs text-ink-3">Researched {relative(latest.created_at)} · written by {latest.provider}</p>
          <div className="prose-chat text-sm leading-relaxed">
            <Markdown remarkPlugins={[remarkGfm]}
              components={{ a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer noopener" className="font-semibold text-jade hover:underline">{children}</a> }}>
              {linkCitations(latest.content, sources)}
            </Markdown>
          </div>
          <ol className="mt-4 space-y-1.5 border-t border-line pt-3">
            {sources.map((s) => (
              <li key={s.n} className="flex items-start gap-2 text-xs">
                <span className="num w-5 shrink-0 text-ink-3">[{s.n}]</span>
                <a href={s.url} target="_blank" rel="noreferrer noopener" className="min-w-0 flex-1 hover:underline">
                  <span className="font-semibold text-ink">{s.title}</span>
                  <span className="text-ink-3"> · {s.domain}{s.published ? ` · ${s.published.slice(0, 10)}` : ""}</span>
                </a>
                <ExternalLink className="mt-0.5 size-3 shrink-0 text-ink-3" />
              </li>
            ))}
          </ol>
          {canWrite ? (
            <div className="mt-4 flex items-center justify-between gap-3">
              <p className="text-[11px] text-ink-3">
                {status.data ? `${status.data.used_this_month} of ${status.data.monthly_limit} web searches used this month.` : null}
              </p>
              <Button size="sm" icon={<NotebookPen className="size-4" />} loading={saveNote.isPending} onClick={() => saveNote.mutate(latest.id)}>
                Save as note
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
