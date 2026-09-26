import { ApiError, getAccessToken, refreshSession } from "@/services/api";
import type { ActionUi } from "./actions";

export type ChatEvent =
  | { type: "conversation"; id: string; title: string }
  | { type: "token"; text: string }
  | { type: "tool_start"; id: string; name: string }
  | { type: "tool_result"; id: string; name: string; ok: boolean; ui: ToolUi | null }
  | { type: "memories"; items: UsedMemory[] }
  | { type: "done"; message_id: string | null; tokens: number; provider: string | null; used_today: number; quota: number }
  | { type: "error"; message: string; code?: string };

export interface RecordsUi {
  kind: "records";
  entity: "company" | "contact" | "lead" | "deal" | "task" | "activity" | "note" | "email";
  title: string;
  total: number;
  rows: { id: string; title: string; subtitle?: string; badge?: string; value?: string; href?: string | null }[];
}

export interface MemoryUi {
  kind: "memory";
  action: "created" | "merged";
  id: string;
  content: string;
  scope: string;
}

export interface WebUi {
  kind: "web";
  title: string;
  rows: { ref: string; title: string; url: string; domain: string; snippet: string; published?: string | null }[];
}

export type ToolUi = RecordsUi | MemoryUi | WebUi | ActionUi;

export interface UsedMemory {
  id: string;
  content: string;
  scope: string;
  source_type: string;
}

export interface ChatBody {
  message: string;
  conversation_id?: string | null;
  page?: { type: "company" | "contact" | "lead" | "deal"; id: string } | null;
  timezone: string;
}

/** POSTs a chat turn and yields server-sent events as they arrive. */
export async function* streamChat(body: ChatBody, signal: AbortSignal, retried = false): AsyncGenerator<ChatEvent> {
  const res = await fetch("/api/ai/chat", {
    method: "POST",
    signal,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
      ...(getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {}),
    },
    body: JSON.stringify(body),
  });

  if (res.status === 401 && !retried && (await refreshSession())) {
    yield* streamChat(body, signal, true);
    return;
  }
  if (!res.ok || !res.body) {
    let message = "The assistant couldn't be reached.";
    try {
      message = (await res.json())?.error?.message ?? message;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, "chat_failed", message);
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let split: number;
    while ((split = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      let event = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (!data) continue;
      yield { type: event, ...JSON.parse(data) } as ChatEvent;
    }
  }
}
