import { useLayoutEffect, useRef, useState, type ElementType, type HTMLAttributes, type ReactNode } from "react";

import { cn } from "@/lib/format";

/**
 * A panel's list that scrolls inside the panel (the page itself never scrolls).
 * Edges fade only where there is more to see, so a faded list is always scrollable.
 */
export function Scroller({ as: As = "div", className, children, ...rest }: HTMLAttributes<HTMLElement> & {
  as?: ElementType;
  children: ReactNode;
}) {
  const ref = useRef<HTMLElement>(null);
  const [edges, setEdges] = useState({ top: false, bottom: false });

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const top = el.scrollTop > 2;
      const bottom = el.scrollTop + el.clientHeight < el.scrollHeight - 2;
      setEdges((e) => (e.top === top && e.bottom === bottom ? e : { top, bottom }));
    };
    update();
    el.addEventListener("scroll", update, { passive: true });
    const resize = new ResizeObserver(update);
    resize.observe(el);
    const content = new MutationObserver(update);
    content.observe(el, { childList: true, subtree: true });
    return () => {
      el.removeEventListener("scroll", update);
      resize.disconnect();
      content.disconnect();
    };
  }, []);

  return (
    <As
      ref={ref}
      className={cn(
        "scroll-quiet min-h-0 overflow-y-auto overscroll-contain",
        edges.top && edges.bottom ? "fade-both" : edges.bottom ? "fade-bottom" : edges.top ? "fade-top" : "",
        className,
      )}
      {...rest}
    >
      {children}
    </As>
  );
}
