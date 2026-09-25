import type { Tint } from "@/components/ui/primitives";

export const LEAD_STATUS: Record<string, { label: string; tint: Tint }> = {
  new: { label: "New", tint: "sky" },
  contacted: { label: "Contacted", tint: "violet" },
  qualified: { label: "Qualified", tint: "emerald" },
  unqualified: { label: "Unqualified", tint: "slate" },
  converted: { label: "Converted", tint: "jade" },
  lost: { label: "Lost", tint: "rose" },
};

export const COMPANY_STATUS: Record<string, { label: string; tint: Tint }> = {
  prospect: { label: "Prospect", tint: "sky" },
  active: { label: "Active", tint: "violet" },
  customer: { label: "Customer", tint: "emerald" },
  churned: { label: "Churned", tint: "rose" },
  inactive: { label: "Inactive", tint: "slate" },
};

export const DEAL_STATUS: Record<string, { label: string; tint: Tint }> = {
  open: { label: "Open", tint: "sky" },
  won: { label: "Won", tint: "emerald" },
  lost: { label: "Lost", tint: "rose" },
};

export const TASK_STATUS: Record<string, { label: string; tint: Tint }> = {
  todo: { label: "To do", tint: "slate" },
  in_progress: { label: "In progress", tint: "sky" },
  completed: { label: "Completed", tint: "emerald" },
  cancelled: { label: "Cancelled", tint: "rose" },
};

export const TASK_PRIORITY: Record<string, { label: string; tint: Tint }> = {
  low: { label: "Low", tint: "slate" },
  medium: { label: "Medium", tint: "sky" },
  high: { label: "High", tint: "amber" },
  urgent: { label: "Urgent", tint: "rose" },
};

export const ACTIVITY_TYPES = [
  { value: "call", label: "Call" },
  { value: "meeting", label: "Meeting" },
  { value: "email", label: "Email" },
  { value: "note", label: "Note" },
  { value: "follow_up", label: "Follow-up" },
];

export const options = (map: Record<string, { label: string }>) =>
  Object.entries(map).map(([value, v]) => ({ value, label: v.label }));
