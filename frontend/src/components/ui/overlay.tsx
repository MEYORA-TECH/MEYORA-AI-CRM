import * as Dialog from "@radix-ui/react-dialog";
import * as Menu from "@radix-ui/react-dropdown-menu";
import { X } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/format";
import { Button } from "./primitives";

/* ---------- Side sheet: used for create/edit forms ---------- */

export function Sheet({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[rgb(14_19_17/0.28)] backdrop-blur-[3px] data-[state=open]:animate-[fade-in_160ms_ease-out]" />
        <Dialog.Content
          className={cn(
            "glass fixed top-3 right-3 bottom-3 z-50 flex w-[min(520px,calc(100vw-24px))] flex-col rounded-[26px]",
            "data-[state=open]:animate-[sheet-in_220ms_cubic-bezier(.2,.8,.2,1)] focus:outline-none",
          )}
          style={{ background: "var(--glass-3)" }}
        >
          <div className="flex items-start justify-between gap-4 border-b border-line px-6 pt-5 pb-4">
            <div>
              <Dialog.Title className="text-lg font-bold tracking-tight">{title}</Dialog.Title>
              {description ? <Dialog.Description className="mt-0.5 text-sm text-ink-3">{description}</Dialog.Description> : <Dialog.Description className="sr-only">{title}</Dialog.Description>}
            </div>
            <Dialog.Close className="focus-ring rounded-full p-1.5 text-ink-3 hover:bg-glass-2 hover:text-ink" aria-label="Close">
              <X className="size-4" />
            </Dialog.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>
          {footer ? <div className="flex justify-end gap-2 border-t border-line px-6 py-4">{footer}</div> : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/* ---------- Modal ---------- */

export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  className,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children?: ReactNode;
  footer?: ReactNode;
  className?: string;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[rgb(14_19_17/0.3)] backdrop-blur-[3px]" />
        <Dialog.Content
          className={cn(
            "glass fixed top-1/2 left-1/2 z-50 w-[min(480px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 rounded-[26px] p-6 focus:outline-none",
            "data-[state=open]:animate-[pop-in_180ms_cubic-bezier(.2,.8,.2,1)]",
            className,
          )}
          style={{ background: "var(--glass-3)" }}
        >
          <Dialog.Title className="text-lg font-bold tracking-tight">{title}</Dialog.Title>
          <Dialog.Description className={description ? "mt-1 text-sm text-ink-2" : "sr-only"}>
            {description ?? title}
          </Dialog.Description>
          {children ? <div className="mt-4">{children}</div> : null}
          {footer ? <div className="mt-6 flex justify-end gap-2">{footer}</div> : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  onConfirm,
  loading,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => void;
  loading?: boolean;
}) {
  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="danger" loading={loading} onClick={onConfirm}>{confirmLabel}</Button>
        </>
      }
    />
  );
}

/* ---------- Dropdown menu ---------- */

export function DropdownMenu({ trigger, children, align = "end" }: { trigger: ReactNode; children: ReactNode; align?: "start" | "end" }) {
  return (
    <Menu.Root>
      <Menu.Trigger asChild>{trigger}</Menu.Trigger>
      <Menu.Portal>
        <Menu.Content
          align={align}
          sideOffset={6}
          className="glass z-50 min-w-48 rounded-2xl p-1.5 data-[state=open]:animate-[pop-in_140ms_ease-out]"
          style={{ background: "var(--glass-3)" }}
        >
          {children}
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  );
}

export function MenuItem({ children, onSelect, danger, icon }: { children: ReactNode; onSelect?: () => void; danger?: boolean; icon?: ReactNode }) {
  return (
    <Menu.Item
      onSelect={onSelect}
      className={cn(
        "flex cursor-pointer items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium outline-none select-none",
        "data-[highlighted]:bg-glass-2",
        danger ? "text-danger" : "text-ink",
      )}
    >
      {icon}
      {children}
    </Menu.Item>
  );
}

export const MenuLabel = ({ children }: { children: ReactNode }) => (
  <Menu.Label className="px-3 pt-2 pb-1 text-[11px] font-semibold tracking-wide text-ink-3 uppercase">{children}</Menu.Label>
);

export const MenuSeparator = () => <Menu.Separator className="my-1 h-px bg-[var(--line)]" />;
