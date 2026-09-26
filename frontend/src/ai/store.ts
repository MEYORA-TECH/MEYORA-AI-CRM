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
}

export const useAiUi = create<AiUiState>((set) => ({
  panelOpen: false,
  setPanelOpen: (panelOpen) => set({ panelOpen }),
  page: null,
  setPage: (page) => set({ page }),
  panelConversationId: null,
  setPanelConversationId: (panelConversationId) => set({ panelConversationId }),
}));
