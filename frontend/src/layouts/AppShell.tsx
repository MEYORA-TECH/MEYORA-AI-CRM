import { Suspense, type ReactNode } from "react";
import { Outlet } from "react-router-dom";

import { Spinner } from "@/components/ui/primitives";
import { cn } from "@/lib/format";
import { CommandPalette } from "./CommandPalette";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export function AppShell() {
  return (
    <div className="min-h-full">
      <div className="ambient" aria-hidden />
      <Sidebar />
      <Topbar />
      <main className="px-4 pt-5 pb-28 md:pr-6 md:pb-10 md:pl-[100px]">
        <Suspense fallback={<div className="flex justify-center py-24"><Spinner /></div>}>
          <Outlet />
        </Suspense>
      </main>
      <CommandPalette />
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
    <div className={cn("rise mb-5 flex flex-wrap items-end justify-between gap-4", className)}>
      <div className="min-w-0">
        {eyebrow ? <div className="mb-1.5 text-xs font-semibold text-ink-3">{eyebrow}</div> : null}
        <h1 className="text-[28px] leading-tight font-extrabold tracking-[-0.03em] text-ink md:text-[32px]">{title}</h1>
        {description ? <p className="mt-1 text-sm text-ink-2">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
