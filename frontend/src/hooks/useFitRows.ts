import { useLayoutEffect, useState, type RefObject } from "react";

/** Table geometry (px). Rows have a fixed height so pages can be sized to the screen. */
export const ROW_HEIGHT = 56;
const TABLE_CHROME = 44 + 50; // header row + pagination footer
const PAGE_CHROME = 290; // top bar, page title and filters, before the table can be measured
const MIN_ROWS = 4;
const MAX_ROWS = 50;

const clamp = (n: number) => Math.max(MIN_ROWS, Math.min(MAX_ROWS, n));

/** A first guess from the window height, so the first request already asks for the right amount. */
export function estimateRows(): number {
  const h = typeof window === "undefined" ? 900 : window.innerHeight;
  return clamp(Math.floor((h - PAGE_CHROME - TABLE_CHROME) / ROW_HEIGHT));
}

/** How many table rows fit in `ref`'s box. Updates (debounced) when the window or layout changes. */
export function useFitRows(ref: RefObject<HTMLElement | null>): number {
  const [rows, setRows] = useState(estimateRows);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    let timer: number | undefined;
    const measure = () => setRows(clamp(Math.floor((el.clientHeight - TABLE_CHROME) / ROW_HEIGHT)));
    measure();
    const observer = new ResizeObserver(() => {
      window.clearTimeout(timer);
      timer = window.setTimeout(measure, 120);
    });
    observer.observe(el);
    return () => {
      observer.disconnect();
      window.clearTimeout(timer);
    };
  }, [ref]);
  return rows;
}
