import { createColumnHelper } from "@tanstack/react-table";
import { Building2, Globe } from "lucide-react";
import { useParams } from "react-router-dom";

import { EntityName } from "@/components/data/EntityPicker";
import { ListPage } from "@/components/data/ListPage";
import { RecordPage, Facts } from "@/components/data/RecordPage";
import { ContactsPanel, DealsPanel, LogActivityButton, NotesPanel, TasksPanel } from "@/components/data/Related";
import { Timeline } from "@/components/data/Timeline";
import { Badge } from "@/components/ui/primitives";
import { companies } from "@/hooks/resources";
import { money, relative } from "@/lib/format";
import { COMPANY_STATUS, options } from "@/lib/status";
import type { Company } from "@/types";
import { COMPANY_FIELDS } from "./fields";

const col = createColumnHelper<Company>();

const columns = [
  col.accessor("name", {
    header: "Company",
    meta: { sortKey: "name" },
    cell: (c) => (
      <div className="min-w-0">
        <p className="truncate font-semibold">{c.getValue()}</p>
        <p className="truncate text-xs text-ink-3">{c.row.original.website?.replace(/^https?:\/\//, "") ?? c.row.original.email ?? ""}</p>
      </div>
    ),
  }),
  col.accessor("industry", { header: "Industry", meta: { sortKey: "industry" }, cell: (c) => c.getValue() ?? "—" }),
  col.accessor("city", { header: "City", meta: { sortKey: "city" }, cell: (c) => c.getValue() ?? "—" }),
  col.accessor("status", {
    header: "Status",
    meta: { sortKey: "status" },
    cell: (c) => <Badge tint={COMPANY_STATUS[c.getValue()].tint}>{COMPANY_STATUS[c.getValue()].label}</Badge>,
  }),
  col.accessor("owner_id", { header: "Owner", cell: (c) => <EntityName kind="member" id={c.getValue()} /> }),
  col.accessor("updated_at", {
    header: "Updated",
    meta: { sortKey: "updated_at", align: "right" },
    cell: (c) => <span className="text-ink-3">{relative(c.getValue())}</span>,
  }),
];

export function CompaniesPage() {
  return (
    <ListPage
      res={companies}
      title="Companies"
      description="Every account you sell to, with its people, deals and history."
      noun="Company"
      columns={columns}
      fields={COMPANY_FIELDS}
      filters={[{ name: "status", label: "Status", options: options(COMPANY_STATUS) }]}
      basePath="/companies"
      emptyIcon={<Building2 className="size-5" />}
      emptyBody="Add the organisations you work with. Converting a lead creates one automatically."
    />
  );
}

export function CompanyDetailPage() {
  const { id = "" } = useParams();
  const query = companies.useOne(id);
  const update = companies.useUpdate();
  const remove = companies.useDelete();

  return (
    <RecordPage<Company>
      backTo="/companies"
      backLabel="Companies"
      noun="Company"
      query={query}
      aiContext={{ type: "company", name: (c) => c.name }}
      title={(c) => c.name}
      subtitle={(c) => [c.industry, [c.city, c.state, c.country].filter(Boolean).join(", ")].filter(Boolean).join(" · ") || undefined}
      badges={(c) => <Badge tint={COMPANY_STATUS[c.status].tint}>{COMPANY_STATUS[c.status].label}</Badge>}
      actions={(c) => <LogActivityButton link={{ company_id: c.id }} />}
      fields={COMPANY_FIELDS}
      saving={update.isPending}
      onSave={(input) => update.mutateAsync({ id, input })}
      onDelete={() => remove.mutateAsync(id)}
      deleting={remove.isPending}
      summary={(c) => (
        <>
          <Facts
            items={[
              { label: "Website", value: c.website ? <a className="inline-flex items-center gap-1 text-jade hover:underline" href={c.website} target="_blank" rel="noreferrer noopener"><Globe className="size-3.5" />{c.website.replace(/^https?:\/\//, "")}</a> : null },
              { label: "Email", value: c.email },
              { label: "Phone", value: c.phone },
              { label: "Employees", value: c.employee_count?.toLocaleString("en-IN") },
              { label: "Annual revenue", value: c.annual_revenue !== null ? <span className="num">{money(c.annual_revenue)}</span> : null },
              { label: "Owner", value: <EntityName kind="member" id={c.owner_id} /> },
              { label: "Added", value: relative(c.created_at) },
            ]}
          />
          {c.tags.length ? (
            <div className="mt-4 flex flex-wrap gap-1.5">{c.tags.map((t) => <Badge key={t}>{t}</Badge>)}</div>
          ) : null}
          {c.description ? <p className="mt-4 border-t border-line pt-4 text-sm whitespace-pre-line text-ink-2">{c.description}</p> : null}
        </>
      )}
      tabs={(c) => [
        { value: "timeline", label: "Timeline", content: <Timeline entity="companies" id={c.id} /> },
        { value: "contacts", label: "Contacts", content: <ContactsPanel companyId={c.id} /> },
        { value: "deals", label: "Deals", content: <DealsPanel filter={{ company_id: c.id }} /> },
        { value: "tasks", label: "Tasks", content: <TasksPanel field="company_id" id={c.id} /> },
        { value: "notes", label: "Notes", content: <NotesPanel field="company_id" id={c.id} /> },
      ]}
    />
  );
}
