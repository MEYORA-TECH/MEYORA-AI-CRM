import type { FieldSpec } from "@/components/data/EntityForm";
import { ACTIVITY_TYPES, COMPANY_STATUS, LEAD_STATUS, TASK_PRIORITY, TASK_STATUS, options } from "@/lib/status";

export const COMPANY_FIELDS: FieldSpec[] = [
  { name: "name", label: "Company name", type: "text", required: true },
  { name: "industry", label: "Industry", type: "text", half: true, placeholder: "Manufacturing" },
  { name: "status", label: "Status", type: "select", half: true, options: options(COMPANY_STATUS) },
  { name: "website", label: "Website", type: "url", half: true, placeholder: "https://" },
  { name: "linkedin_url", label: "LinkedIn", type: "url", half: true, placeholder: "https://linkedin.com/company/…" },
  { name: "email", label: "Email", type: "email", half: true },
  { name: "phone", label: "Phone", type: "tel", half: true },
  { name: "employee_count", label: "Employees", type: "number", half: true, min: 0 },
  { name: "annual_revenue", label: "Annual revenue (₹)", type: "money", min: 0 },
  { name: "address", label: "Address", type: "text" },
  { name: "city", label: "City", type: "text", half: true },
  { name: "state", label: "State", type: "text", half: true },
  { name: "country", label: "Country", type: "text", half: true },
  { name: "owner_id", label: "Owner", type: "ref", kind: "member", half: true },
  { name: "tags", label: "Tags", type: "tags" },
  { name: "description", label: "Description", type: "textarea" },
];

export const CONTACT_FIELDS: FieldSpec[] = [
  { name: "first_name", label: "First name", type: "text", required: true, half: true },
  { name: "last_name", label: "Last name", type: "text", half: true },
  { name: "job_title", label: "Job title", type: "text", half: true },
  { name: "company_id", label: "Company", type: "ref", kind: "company", half: true },
  { name: "email", label: "Email", type: "email", half: true },
  { name: "phone", label: "Phone", type: "tel", half: true },
  { name: "linkedin_url", label: "LinkedIn", type: "url", placeholder: "https://linkedin.com/in/…" },
  { name: "city", label: "City", type: "text", half: true },
  { name: "country", label: "Country", type: "text", half: true },
  { name: "owner_id", label: "Owner", type: "ref", kind: "member", half: true },
  { name: "tags", label: "Tags", type: "tags" },
  { name: "description", label: "Background", type: "textarea" },
];

export const LEAD_FIELDS: FieldSpec[] = [
  { name: "name", label: "Name", type: "text", required: true, half: true },
  { name: "company_name", label: "Company", type: "text", half: true },
  { name: "job_title", label: "Job title", type: "text", half: true },
  { name: "industry", label: "Industry", type: "text", half: true },
  { name: "email", label: "Email", type: "email", half: true },
  { name: "phone", label: "Phone", type: "tel", half: true },
  { name: "linkedin_url", label: "LinkedIn", type: "url", half: true, placeholder: "https://linkedin.com/in/…" },
  { name: "source", label: "Source", type: "text", half: true, placeholder: "Referral, website, event…" },
  {
    name: "status", label: "Status", type: "select", half: true,
    options: options(LEAD_STATUS).filter((o) => o.value !== "converted"),
  },
  { name: "score", label: "Score (0–100)", type: "number", half: true, min: 0, max: 100 },
  { name: "owner_id", label: "Owner", type: "ref", kind: "member", half: true },
  { name: "tags", label: "Tags", type: "tags" },
  { name: "description", label: "Notes", type: "textarea" },
];

export const dealFields = (stageOptions: { value: string; label: string }[]): FieldSpec[] => [
  { name: "name", label: "Deal name", type: "text", required: true },
  { name: "amount", label: "Amount", type: "money", half: true, min: 0 },
  { name: "currency", label: "Currency", type: "select", half: true, options: ["INR", "USD", "EUR", "GBP", "AED", "SGD"].map((c) => ({ value: c, label: c })) },
  { name: "stage_id", label: "Stage", type: "select", half: true, options: stageOptions },
  { name: "expected_close_date", label: "Expected close", type: "date", half: true },
  { name: "company_id", label: "Company", type: "ref", kind: "company", half: true },
  { name: "contact_id", label: "Contact", type: "ref", kind: "contact", half: true },
  { name: "probability", label: "Probability %", type: "number", half: true, min: 0, max: 100, hint: "Defaults to the stage's value." },
  { name: "owner_id", label: "Owner", type: "ref", kind: "member", half: true },
  { name: "source", label: "Source", type: "text" },
  { name: "tags", label: "Tags", type: "tags" },
  { name: "description", label: "Description", type: "textarea" },
];

export const TASK_FIELDS: FieldSpec[] = [
  { name: "title", label: "Title", type: "text", required: true },
  { name: "due_at", label: "Due", type: "datetime", half: true },
  { name: "priority", label: "Priority", type: "select", half: true, options: options(TASK_PRIORITY) },
  { name: "status", label: "Status", type: "select", half: true, options: options(TASK_STATUS) },
  { name: "assignee_id", label: "Assignee", type: "ref", kind: "member", half: true },
  { name: "company_id", label: "Company", type: "ref", kind: "company", half: true },
  { name: "contact_id", label: "Contact", type: "ref", kind: "contact", half: true },
  { name: "deal_id", label: "Deal", type: "ref", kind: "deal", half: true },
  { name: "lead_id", label: "Lead", type: "ref", kind: "lead", half: true },
  { name: "description", label: "Details", type: "textarea" },
];

export const ACTIVITY_FIELDS: FieldSpec[] = [
  { name: "type", label: "Type", type: "select", half: true, options: ACTIVITY_TYPES, required: true },
  { name: "occurred_at", label: "When", type: "datetime", half: true, hint: "A future time logs it as planned." },
  { name: "subject", label: "Subject", type: "text", required: true },
  { name: "duration_minutes", label: "Duration (min)", type: "number", half: true, min: 0 },
  { name: "outcome", label: "Outcome", type: "text", half: true },
  { name: "company_id", label: "Company", type: "ref", kind: "company", half: true },
  { name: "contact_id", label: "Contact", type: "ref", kind: "contact", half: true },
  { name: "deal_id", label: "Deal", type: "ref", kind: "deal", half: true },
  { name: "lead_id", label: "Lead", type: "ref", kind: "lead", half: true },
  { name: "body", label: "Notes", type: "textarea" },
];
