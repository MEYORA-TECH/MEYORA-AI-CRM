import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));

/** INR uses lakh/crore grouping (₹12,50,000); other currencies use their own locale. */
export function money(amount: number | null | undefined, currency = "INR", opts: { compact?: boolean } = {}) {
  if (amount === null || amount === undefined) return "—";
  const locale = currency === "INR" ? "en-IN" : undefined;
  if (opts.compact && currency === "INR") {
    if (Math.abs(amount) >= 1e7) return `₹${trim(amount / 1e7)} Cr`;
    if (Math.abs(amount) >= 1e5) return `₹${trim(amount / 1e5)} L`;
  }
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    maximumFractionDigits: opts.compact ? 1 : 0,
    notation: opts.compact && currency !== "INR" ? "compact" : "standard",
  }).format(amount);
}

const trim = (n: number) => (Math.round(n * 10) / 10).toString();

const dateFmt = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });
const shortFmt = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" });
const timeFmt = new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit" });

export function date(value: string | null | undefined) {
  return value ? dateFmt.format(new Date(value)) : "—";
}

export function dateTime(value: string | null | undefined) {
  if (!value) return "—";
  const d = new Date(value);
  return `${shortFmt.format(d)}, ${timeFmt.format(d)}`;
}

export function relative(value: string | null | undefined) {
  if (!value) return "—";
  const diff = new Date(value).getTime() - Date.now();
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 31536e6], ["month", 2592e6], ["week", 6048e5], ["day", 864e5], ["hour", 36e5], ["minute", 6e4],
  ];
  for (const [unit, ms] of units) if (abs >= ms) return rtf.format(Math.round(diff / ms), unit);
  return "just now";
}

export function initials(name: string | null | undefined) {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

export function label(value: string | null | undefined) {
  if (!value) return "—";
  return value.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

/** Converts an ISO timestamp to the value a datetime-local input expects. */
export function toLocalInput(value: string | null | undefined) {
  if (!value) return "";
  const d = new Date(value);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export const timeZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Kolkata";
