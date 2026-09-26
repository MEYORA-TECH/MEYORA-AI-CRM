import * as Dialog from "@radix-ui/react-dialog";
import { Maximize2, Plus, X } from "lucide-react";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { IconButton } from "@/components/ui/primitives";
import { Composer, Messages, Spark, UsageLine, Welcome } from "./ChatThread";
import { useAiUi } from "./store";
import { useAiStatus, useChat } from "./useChat";

/** Right-side glass drawer: the assistant, aware of the record on screen. Ctrl+J toggles it. */
export function AIPanel() {
  const { panelOpen, setPanelOpen, page, panelConversationId, setPanelConversationId } = useAiUi();
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
          style={{ background: "var(--glass-2)" }}
        >
          <div className="flex items-center gap-2 border-b border-line px-4 py-3">
            <Spark className="size-7" />
            <div className="min-w-0 flex-1">
              <Dialog.Title className="text-[15px] font-bold tracking-tight">Meyora</Dialog.Title>
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

          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
            {chat.items.length === 0 && !chat.loading ? (
              <Welcome page={page} onPick={(t) => chat.send(t, page)} />
            ) : (
              <Messages items={chat.items} compact />
            )}
          </div>

          <div className="flex flex-col gap-2 border-t border-line p-3">
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
