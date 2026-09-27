import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { timeZone } from "@/lib/format";
import { api, describeError } from "@/services/api";
import type {
  Activity, Board, Company, Contact, Dashboard, Deal, Lead, LeadConvertInput, LeadConvertResult,
  Member, Note, Page, Pipeline, Task, TimelineItem,
} from "@/types";

export type ListParams = Record<string, string | number | boolean | string[] | null | undefined>;

/** Shared CRUD hooks for one REST collection, e.g. `/companies`. */
export function resource<T extends { id: string }, TInput = Partial<T>>(path: string, noun: string) {
  const key = [path] as const;

  return {
    key,
    useList(params: ListParams = {}, opts: { enabled?: boolean } = {}) {
      return useQuery({
        queryKey: [...key, "list", params],
        queryFn: () => api.get<Page<T>>(path, params),
        placeholderData: keepPreviousData,
        enabled: opts.enabled,
      });
    },
    useOne(id: string | undefined) {
      const qc = useQueryClient();
      // Opening a record from a list shows the row already loaded, then refreshes it quietly.
      let fromList: T | undefined;
      for (const [, page] of qc.getQueriesData<Page<T>>({ queryKey: [...key, "list"] })) {
        fromList = page?.items.find((row) => row.id === id);
        if (fromList) break;
      }
      return useQuery({
        queryKey: [...key, "one", id],
        queryFn: () => api.get<T>(`${path}/${id}`),
        enabled: Boolean(id),
        // Records are plain objects; the cast only satisfies the library's "not a function" guard on generic T.
        placeholderData: fromList as never,
      });
    },
    useCreate() {
      const qc = useQueryClient();
      return useMutation({
        mutationFn: (input: TInput) => api.post<T>(path, input),
        onSuccess: () => {
          qc.invalidateQueries({ queryKey: key });
          qc.invalidateQueries({ queryKey: ["dashboard"] });
          qc.invalidateQueries({ queryKey: ["timeline"] });
          toast.success(`${noun} created`);
        },
        onError: (e) => toast.error(describeError(e)),
      });
    },
    useUpdate() {
      const qc = useQueryClient();
      return useMutation({
        mutationFn: ({ id, input }: { id: string; input: Partial<TInput> }) => api.patch<T>(`${path}/${id}`, input),
        onSuccess: (row) => {
          qc.setQueryData([...key, "one", row.id], row);
          qc.invalidateQueries({ queryKey: key });
          qc.invalidateQueries({ queryKey: ["dashboard"] });
          qc.invalidateQueries({ queryKey: ["timeline"] });
        },
        onError: (e) => toast.error(describeError(e)),
      });
    },
    useDelete() {
      const qc = useQueryClient();
      return useMutation({
        mutationFn: (id: string) => api.delete(`${path}/${id}`),
        onSuccess: () => {
          qc.invalidateQueries({ queryKey: key });
          qc.invalidateQueries({ queryKey: ["dashboard"] });
          toast.success(`${noun} deleted`);
        },
        onError: (e) => toast.error(describeError(e)),
      });
    },
  };
}

export const companies = resource<Company>("/companies", "Company");
export const contacts = resource<Contact>("/contacts", "Contact");
export const leads = resource<Lead>("/leads", "Lead");
export const deals = resource<Deal>("/deals", "Deal");
export const activities = resource<Activity>("/activities", "Activity");
export const tasks = resource<Task>("/tasks", "Task");
export const notes = resource<Note>("/notes", "Note");

export function usePipelines() {
  return useQuery({ queryKey: ["/pipelines"], queryFn: () => api.get<Pipeline[]>("/pipelines"), staleTime: 60_000 });
}

export function useMembers() {
  return useQuery({
    queryKey: ["/organization/members"],
    queryFn: () => api.get<Member[]>("/organization/members"),
    staleTime: 60_000,
  });
}

const dashboardQuery = (tz: string) => ({
  queryKey: ["dashboard", tz],
  queryFn: () => api.get<Dashboard>("/dashboard", { tz }),
});

export function useDashboard(tz: string) {
  return useQuery(dashboardQuery(tz));
}

const DEFAULT_LIST = { page: 1, page_size: 25 };
const LISTS: Record<string, string> = { "/companies": "/companies", "/contacts": "/contacts", "/leads": "/leads" };

/** Start loading a screen's first data when the pointer is on its link, so it opens already filled. */
export function usePrefetchRoute() {
  const qc = useQueryClient();
  return (to: string) => {
    if (to === "/") {
      void qc.prefetchQuery(dashboardQuery(timeZone()));
    } else if (LISTS[to]) {
      void qc.prefetchQuery({
        queryKey: [LISTS[to], "list", DEFAULT_LIST],
        queryFn: () => api.get<Page<unknown>>(LISTS[to], DEFAULT_LIST),
      });
    }
  };
}

export function useTimeline(entity: "companies" | "contacts" | "leads" | "deals", id: string | undefined) {
  return useQuery({
    queryKey: ["timeline", entity, id],
    queryFn: () => api.get<TimelineItem[]>(`/timeline/${entity}/${id}`),
    enabled: Boolean(id),
  });
}

export function useBoard(pipelineId: string | undefined) {
  return useQuery({
    queryKey: ["/deals", "board", pipelineId],
    queryFn: () => api.get<Board>("/deals/board", { pipeline_id: pipelineId }),
  });
}

export function useMoveDeal(pipelineId: string | undefined) {
  const qc = useQueryClient();
  const boardKey = ["/deals", "board", pipelineId];
  return useMutation({
    mutationFn: ({ dealId, stageId }: { dealId: string; stageId: string }) =>
      api.post<Deal>(`/deals/${dealId}/move`, { stage_id: stageId }),
    // Move the card immediately; roll back if the server refuses.
    onMutate: async ({ dealId, stageId }) => {
      await qc.cancelQueries({ queryKey: boardKey });
      const previous = qc.getQueryData<Board>(boardKey);
      if (previous) {
        const deal = previous.columns.flatMap((c) => c.deals).find((d) => d.id === dealId);
        if (deal) {
          qc.setQueryData<Board>(boardKey, {
            ...previous,
            columns: previous.columns.map((c) => {
              const without = c.deals.filter((d) => d.id !== dealId);
              const moved = c.stage_id === stageId ? [{ ...deal, stage_id: stageId }, ...without] : without;
              const delta = moved.length - c.deals.length;
              return {
                ...c,
                deals: moved,
                count: c.count + delta,
                total_amount: c.total_amount + delta * deal.amount,
              };
            }),
          });
        }
      }
      return { previous };
    },
    onError: (e, _v, context) => {
      if (context?.previous) qc.setQueryData(boardKey, context.previous);
      toast.error(describeError(e));
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["/deals"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["timeline"] });
    },
  });
}

export function useConvertLead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: LeadConvertInput }) =>
      api.post<LeadConvertResult>(`/leads/${id}/convert`, input),
    onSuccess: () => {
      for (const k of ["/leads", "/companies", "/contacts", "/deals", "dashboard", "timeline"]) {
        qc.invalidateQueries({ queryKey: [k] });
      }
      toast.success("Lead converted");
    },
    onError: (e) => toast.error(describeError(e)),
  });
}
