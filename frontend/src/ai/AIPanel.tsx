import * as Dialog from "@radix-ui/react-dialog";
import { Maximize2, Plus, X } from "@/components/icons";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { ErrorBoundary } from "@/components/ErrorBoundary";
import { IconButton } from "@/components/ui/primitives";
import { Composer, Messages, UsageLine, Welcome } from "./ChatThread";
import { Orb } from "./Orb";
import { useAiUi } from "./store";
import { useAiStatus, useChat } from "./useChat";

/** Right-side glass drawer: the assistant, aware of the record on screen. Ctrl+J toggles it. */
export function AIPanel() {
  const { panelOpen, setPanelOpen, page, panelConversationId, setPanelConversationId, pendingPrompt, takePendingPrompt } = useAiUi();
  const chat = useChat(panelConversationId, setPanelConversationId);
  const status = useAiStatus();
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j") {
        e.preventDefault();
        setPanelOpen(!useAiUi.getState().panelOpen);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setPanelOpen]);

  useEffect(() => {
    if (!pendingPrompt || chat.streaming) return;
    const prompt = takePendingPrompt();
    if (prompt) {
      chat.reset();
      chat.send(prompt, page);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingPrompt]);

  const newChat = () => {
    chat.reset();
    setPanelConversationId(null);
  };

  return (
    <Dialog.Root open={panelOpen} onOpenChange={setPanelOpen} modal={false}>
      <Dialog.Portal>
        <Dialog.Content
          onInteractOutside={(e) => e.preventDefault()}
          className="glass fixed top-3 right-3 bottom-3 z-40 flex w-[min(440px,calc(100vw-24px))] flex-col rounded-[26px] focus:outline-none data-[state=open]:animate-[sheet-in_220ms_cubic-bezier(.2,.8,.2,1)]"
          style={{ background: "var(--sheet)", backdropFilter: "none", WebkitBackdropFilter: "none" }}
        >
          <div className="flex flex-none items-center gap-2.5 border-b border-line px-4 py-3">
            <Orb className="size-8" thinking={chat.streaming} />
            <div className="min-w-0 flex-1">
              <Dialog.Title className="font-display text-[15px] font-bold tracking-[-0.01em]">Meyora</Dialog.Title>
              <Dialog.Description className="text-[11px] text-ink-3">Reads your CRM · Ctrl J</Dialog.Description>
            </div>
            <IconButton label="New chat" onClick={newChat}><Plus className="size-4" /></IconButton>
            <IconButton
              label="Open full screen"
              onClick={() => {
                setPanelOpen(false);
                navigate(panelConversationId ? `/assistant/${panelConversationId}` : "/assistant");
              }}
            >
              <Maximize2 className="size-4" />
            </IconButton>
            <Dialog.Close asChild>
              <IconButton label="Close"><X className="size-4" /></IconButton>
            </Dialog.Close>
          </div>

          <div className="scroll-quiet min-h-0 flex-1 overflow-y-auto px-4 py-4">
            {chat.items.length === 0 && !chat.loading ? (
              <Welcome compact page={page} onPick={(t) => chat.send(t, page)} />
            ) : (
              <ErrorBoundary resetKey={chat.items.length} label="This conversation couldn't be shown.">
                <Messages items={chat.items} compact />
              </ErrorBoundary>
            )}
          </div>

          <div className="flex flex-none flex-col gap-2 p-3 pt-1">
            <Composer
              autoFocus
              page={page}
              streaming={chat.streaming}
              disabled={status.data ? !status.data.configured : false}
              onSend={(t) => chat.send(t, page)}
              onStop={chat.stop}
            />
            <UsageLine />
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
