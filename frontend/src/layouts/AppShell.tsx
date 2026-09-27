import { Suspense, type ReactNode } from "react";
import { Outlet } from "react-router-dom";

import { AIPanel } from "@/ai/AIPanel";
import { Spinner } from "@/components/ui/primitives";
import { cn } from "@/lib/format";
import { CommandPalette } from "./CommandPalette";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export function AppShell() {
  return (
    // The window never scrolls: the shell is exactly one screen tall and pages fit inside it.
    <div className="flex h-dvh flex-col overflow-hidden">
      <div className="ambient" aria-hidden />
      <Sidebar />
      <Topbar />
      <main className="scroll-quiet flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain px-4 pt-4 pb-24 md:pr-6 md:pb-5 md:pl-[100px]">
        <Suspense fallback={<div className="flex justify-center py-24"><Spinner /></div>}>
          <Outlet />
        </Suspense>
      </main>
      <CommandPalette />
      <AIPanel />
    </div>
  );
}

/** Page title row: large tight heading, a one-line description, and actions. */
export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  eyebrow?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("rise mb-4 flex flex-none flex-wrap items-end justify-between gap-4", className)}>
      <div className="min-w-0">
        {eyebrow ? <div className="mb-1.5 text-xs font-semibold text-ink-3">{eyebrow}</div> : null}
        <h1 className="font-display text-[24px] leading-tight font-bold tracking-[-0.03em] text-ink md:text-[28px]">{title}</h1>
        {description ? <p className="mt-1 text-sm text-ink-2">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
