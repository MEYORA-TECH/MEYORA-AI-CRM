import type { ReactNode } from "react";

import { NilaLogo } from "@/components/icons";

export function AuthLayout({ title, subtitle, children, footer }: { title: string; subtitle: string; children: ReactNode; footer: ReactNode }) {
  return (
    <div className="flex min-h-full items-center justify-center px-4 py-10">
      <div className="ambient" aria-hidden />
      <div className="rise w-full max-w-[420px]">
        <div className="mb-6">
          <NilaLogo wordmark="h-10" endorsement="text-[12px]" />
        </div>
        <div className="glass rounded-[28px] p-7 sm:p-8">
          <h1 className="font-display text-[26px] leading-tight font-bold tracking-[-0.025em]">{title}</h1>
          <p className="mt-1.5 text-sm text-ink-2">{subtitle}</p>
          <div className="mt-6">{children}</div>
        </div>
        <p className="mt-5 text-center text-sm text-ink-2">{footer}</p>
      </div>
    </div>
  );
}
