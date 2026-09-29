import { useId } from "react";

import { cn } from "@/lib/format";

/**
 * Nila, the assistant: a frosted ice orb carrying Nila's crescent.
 * While thinking it breathes (a soft halo) and a sheen turns across its surface.
 * Decorative only; the surrounding UI says what's happening in words.
 */
export function Orb({ className, thinking }: { className?: string; thinking?: boolean }) {
  const id = useId().replace(/:/g, "");
  return (
    <span aria-hidden className={cn("orb relative inline-grid shrink-0 place-items-center", thinking && "orb-thinking", className)}>
      <svg viewBox="0 0 48 48" className="relative z-[1] size-full">
        <defs>
          <radialGradient id={`${id}b`} cx="34%" cy="28%" r="78%">
            <stop offset="0" stopColor="#e4eff6" />
            <stop offset="0.42" stopColor="#86adc6" />
            <stop offset="0.78" stopColor="#3f6a84" />
            <stop offset="1" stopColor="#23394a" />
          </radialGradient>
          <radialGradient id={`${id}s`} cx="33%" cy="22%" r="34%">
            <stop offset="0" stopColor="#ffffff" stopOpacity="0.95" />
            <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
          </radialGradient>
          <linearGradient id={`${id}r`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#ffffff" stopOpacity="0.7" />
            <stop offset="1" stopColor="#ffffff" stopOpacity="0.08" />
          </linearGradient>
        </defs>
        <circle cx="24" cy="24" r="22" fill={`url(#${id}b)`} />
        <circle cx="24" cy="24" r="22" fill={`url(#${id}s)`} />
        <path d="M231.94 129.69A104 104 0 1 1 122.31 20.06A80.89 80.89 0 1 0 231.94 129.69Z" fill="#ffffff" fillOpacity="0.96"
          transform="translate(10.2 10.2) scale(0.1078)" />
        <circle cx="24" cy="24" r="21.4" fill="none" stroke={`url(#${id}r)`} strokeWidth="1.2" />
      </svg>
    </span>
  );
}
