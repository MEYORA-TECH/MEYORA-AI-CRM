import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, describeError } from "@/services/api";
import { timeZone } from "@/lib/format";
import { streamChat, type ToolUi, type UsedMemory } from "./stream";
import type { PageContext } from "./store";

export interface ChatItem {
  key: string;
  role: "user" | "assistant" | "tool";
  content: string;
  toolName?: string;
  ui?: ToolUi | null;
  memories?: UsedMemory[];
  pending?: boolean;
  error?: string;
  provider?: string | null;
  /** A passing note while the answer is on hold, e.g. waiting out a free-tier limit. */
  status?: string;
}

interface StoredMessage {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string | null;
  tool_name: string | null;
  ui: ToolUi | null;
  provider: string | null;
}

export interface AiStatus {
  configured: boolean;
  providers: string[];
  used_today: number;
  quota: number;
}

export function useAiStatus() {
  return useQuery({ queryKey: ["ai", "status"], queryFn: () => api.get<AiStatus>("/ai/status"), staleTime: 30_000 });
}

let seq = 0;
const key = () => `local-${++seq}`;

/** State and streaming for one conversation. Pass null to start a new one. */
export function useChat(conversationId: string | null, onConversation?: (id: string) => void) {
  const qc = useQueryClient();
  const [items, setItems] = useState<ChatItem[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [loading, setLoading] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const current = useRef<string | null>(conversationId);
  // Set when this hook created the conversation, so it doesn't reload what it just streamed.
  const created = useRef<string | null>(null);

  useEffect(() => {
    current.current = conversationId;
    if (!conversationId) {
      setItems([]);
      return;
    }
    if (created.current === conversationId) return;
    let cancelled = false;
    setLoading(true);
    api
      .get<StoredMessage[]>(`/ai/conversations/${conversationId}/messages`)
      .then((rows) => {
        if (cancelled) return;
        setItems(
          rows.map((m) => ({
            key: m.id,
            role: m.role,
            content: m.content ?? "",
            toolName: m.tool_name ?? undefined,
            ui: m.ui,
            provider: m.provider,
          })),
        );
      })
      .catch((e) => !cancelled && setItems([{ key: key(), role: "assistant", content: "", error: describeError(e) }]))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  useEffect(() => () => abort.current?.abort(), []);

  const send = useCallback(
    async (message: string, page: PageContext | null) => {
      const text = message.trim();
      if (!text || streaming) return;
      const assistantKey = key();
      setItems((xs) => [...xs, { key: key(), role: "user", content: text }, { key: assistantKey, role: "assistant", content: "", pending: true }]);
      setStreaming(true);
      const controller = new AbortController();
      abort.current = controller;

      const patchAssistant = (patch: Partial<ChatItem> | ((i: ChatItem) => Partial<ChatItem>)) =>
        setItems((xs) => xs.map((i) => (i.key === assistantKey ? { ...i, ...(typeof patch === "function" ? patch(i) : patch) } : i)));

      try {
        for await (const ev of streamChat(
          { message: text, conversation_id: current.current, page: page ? { type: page.type, id: page.id } : null, timezone: timeZone() },
          controller.signal,
        )) {
          if (ev.type === "conversation") {
            if (!current.current) {
              created.current = ev.id;
              current.current = ev.id;
              onConversation?.(ev.id);
            }
          } else if (ev.type === "memories") {
            patchAssistant({ memories: ev.items });
          } else if (ev.type === "status") {
            patchAssistant({ status: ev.message });
          } else if (ev.type === "token") {
            patchAssistant((i) => ({ content: i.content + ev.text, status: undefined }));
          } else if (ev.type === "tool_start") {
            // Tool steps appear above the answer they feed.
            setItems((xs) => {
              const at = xs.findIndex((i) => i.key === assistantKey);
              const step: ChatItem = { key: `tool-${ev.id}`, role: "tool", content: "", toolName: ev.name, pending: true };
              const next = [...xs.slice(0, at), step, ...xs.slice(at)];
              return next.map((i) => (i.key === assistantKey ? { ...i, status: undefined } : i));
            });
          } else if (ev.type === "tool_result") {
            setItems((xs) => xs.map((i) => (i.key === `tool-${ev.id}` ? { ...i, pending: false, ui: ev.ui, error: ev.ok ? undefined : "failed" } : i)));
          } else if (ev.type === "error") {
            patchAssistant({ pending: false, error: ev.message, status: undefined });
          } else if (ev.type === "done") {
            patchAssistant({ pending: false, provider: ev.provider, status: undefined });
            qc.setQueryData<AiStatus>(["ai", "status"], (s) => (s ? { ...s, used_today: ev.used_today, quota: ev.quota } : s));
          }
        }
      } catch (e) {
        if (!controller.signal.aborted) patchAssistant({ pending: false, error: describeError(e) });
      } finally {
        patchAssistant((i) => ({ pending: false, content: i.content || (i.error ? "" : controller.signal.aborted ? "Stopped." : i.content) }));
        setStreaming(false);
        qc.invalidateQueries({ queryKey: ["ai", "conversations"] });
      }
    },
    [streaming, onConversation, qc],
  );

  const stop = useCallback(() => abort.current?.abort(), []);
  const reset = useCallback(() => {
    abort.current?.abort();
    created.current = null;
    current.current = null;
    setItems([]);
  }, []);

  return { items, send, stop, reset, streaming, loading };
}
