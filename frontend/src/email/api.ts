import { useQuery } from "@tanstack/react-query";

import { api } from "@/services/api";
import type { components } from "@/types/api";
import type { Page } from "@/types";

export type EmailThread = components["schemas"]["ThreadOut"];
export type EmailThreadDetail = components["schemas"]["ThreadDetail"];
export type MailAccount = components["schemas"]["MailAccountOut"];
export type GmailStatus = components["schemas"]["GmailStatus"];

export interface AuthProviders {
  password: boolean;
  google: boolean;
  gmail: boolean;
}

export function useAuthProviders() {
  return useQuery({
    queryKey: ["auth", "providers"],
    queryFn: () => api.get<AuthProviders>("/auth/providers"),
    staleTime: 5 * 60_000,
  });
}

export function useThreads(params: Record<string, string | number | undefined>) {
  return useQuery({
    queryKey: ["emails", "threads", params],
    queryFn: () => api.get<Page<EmailThread>>("/emails/threads", { page_size: 30, ...params }),
  });
}

export function useThread(id: string | undefined) {
  return useQuery({
    queryKey: ["emails", "thread", id],
    queryFn: () => api.get<EmailThreadDetail>(`/emails/threads/${id}`),
    enabled: Boolean(id),
  });
}

export function useGmail() {
  return useQuery({ queryKey: ["gmail"], queryFn: () => api.get<GmailStatus>("/integrations/gmail") });
}

export interface Participant {
  email: string;
  name?: string | null;
}

/** The API types participants loosely (JSON); they are always {email, name}. */
export const people = (t: { participants: unknown[] }) => t.participants as Participant[];

export function participantsLabel(t: { participants: unknown[] }, own?: string) {
  const list = people(t).filter((p) => p.email !== own?.toLowerCase());
  const names = list.slice(0, 3).map((p) => p.name || p.email);
  return names.join(", ") + (list.length > 3 ? ` +${list.length - 3}` : "");
}
