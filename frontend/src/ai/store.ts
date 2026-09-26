import { create } from "zustand";

export interface PageContext {
  type: "company" | "contact" | "lead" | "deal";
  id: string;
  name: string;
}

interface AiUiState {
  panelOpen: boolean;
  setPanelOpen: (open: boolean) => void;
  /** The record on screen; the assistant uses it to resolve "this deal". */
  page: PageContext | null;
  setPage: (page: PageContext | null) => void;
  /** Conversation shown in the side panel (the Assistant page keeps its own). */
  panelConversationId: string | null;
  setPanelConversationId: (id: string | null) => void;
  /** Open the panel and send this in a new conversation (e.g. "Summarise this thread"). */
  pendingPrompt: string | null;
  ask: (prompt: string) => void;
  takePendingPrompt: () => string | null;
}

export const useAiUi = create<AiUiState>((set, get) => ({
  panelOpen: false,
  setPanelOpen: (panelOpen) => set({ panelOpen }),
  page: null,
  setPage: (page) => set({ page }),
  panelConversationId: null,
  setPanelConversationId: (panelConversationId) => set({ panelConversationId }),
  pendingPrompt: null,
  ask: (prompt) => set({ pendingPrompt: prompt, panelOpen: true, panelConversationId: null }),
  takePendingPrompt: () => {
    const prompt = get().pendingPrompt;
    if (prompt) set({ pendingPrompt: null });
    return prompt;
  },
}));
