import { createColumnHelper } from "@tanstack/react-table";
import { UsersRound } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { EntityName } from "@/components/data/EntityPicker";
import { ListPage } from "@/components/data/ListPage";
import { Facts, RecordPage } from "@/components/data/RecordPage";
import { DealsPanel, LogActivityButton, NotesPanel, TasksPanel } from "@/components/data/Related";
import { RecordMemoryPanel } from "@/ai/memories";
import { RecordEmailsPanel } from "@/email/components";
import { Timeline } from "@/components/data/Timeline";
import { Avatar, Badge } from "@/components/ui/primitives";
import { contacts } from "@/hooks/resources";
import { relative } from "@/lib/format";
import type { Contact } from "@/types";
import { CONTACT_FIELDS } from "./fields";

const col = createColumnHelper<Contact>();

const columns = [
  col.accessor("first_name", {
    header: "Name",
    meta: { sortKey: "first_name" },
    cell: (c) => (
      <div className="flex items-center gap-3">
        <Avatar name={c.row.original.full_name} size={30} />
        <div className="min-w-0">
          <p className="truncate font-semibold">{c.row.original.full_name}</p>
          <p className="truncate text-xs text-ink-3">{c.row.original.job_title ?? ""}</p>
        </div>
      </div>
    ),
  }),
  col.accessor((r) => r.company?.name, { id: "company", header: "Company", cell: (c) => c.getValue() ?? "—" }),
  col.accessor("email", { header: "Email", meta: { sortKey: "email" }, cell: (c) => c.getValue() ?? "—" }),
  col.accessor("phone", { header: "Phone", cell: (c) => <span className="num">{c.getValue() ?? "—"}</span> }),
  col.accessor("owner_id", { header: "Owner", cell: (c) => <EntityName kind="member" id={c.getValue()} /> }),
  col.accessor("updated_at", {
    header: "Updated",
    meta: { sortKey: "updated_at", align: "right" },
    cell: (c) => <span className="text-ink-3">{relative(c.getValue())}</span>,
  }),
];

export function ContactsPage() {
  return (
    <ListPage
      res={contacts}
      title="Contacts"
      description="The people behind your accounts and what you've discussed with them."
      noun="Contact"
      columns={columns}
      fields={CONTACT_FIELDS}
      basePath="/contacts"
      emptyIcon={<UsersRound className="size-5" />}
      emptyBody="Add the people you talk to. Link each one to a company to see them together."
    />
  );
}

export function ContactDetailPage() {
  const { id = "" } = useParams();
  const query = contacts.useOne(id);
  const update = contacts.useUpdate();
  const remove = contacts.useDelete();

  return (
    <RecordPage<Contact>
      backTo="/contacts"
      backLabel="Contacts"
      noun="Contact"
      query={query}
      aiContext={{ type: "contact", name: (c) => c.full_name }}
      title={(c) => (
        <span className="flex items-center gap-3">
          <Avatar name={c.full_name} size={40} /> {c.full_name}
        </span>
      )}
      subtitle={(c) =>
        c.job_title || c.company ? (
          <>
            {c.job_title}
            {c.job_title && c.company ? " at " : ""}
            {c.company ? <Link className="font-semibold text-jade hover:underline" to={`/companies/${c.company.id}`}>{c.company.name}</Link> : null}
          </>
        ) : undefined
      }
      actions={(c) => <LogActivityButton link={{ contact_id: c.id, ...(c.company_id ? { company_id: c.company_id } : {}) }} />}
      fields={CONTACT_FIELDS}
      saving={update.isPending}
      onSave={(input) => update.mutateAsync({ id, input })}
      onDelete={() => remove.mutateAsync(id)}
      deleting={remove.isPending}
      summary={(c) => (
        <>
          <Facts
            items={[
              { label: "Email", value: c.email ? <a className="text-jade hover:underline" href={`mailto:${c.email}`}>{c.email}</a> : null },
              { label: "Phone", value: c.phone ? <a className="num hover:underline" href={`tel:${c.phone}`}>{c.phone}</a> : null },
              { label: "LinkedIn", value: c.linkedin_url ? <a className="text-jade hover:underline" href={c.linkedin_url} target="_blank" rel="noreferrer noopener">Profile</a> : null },
              { label: "Location", value: [c.city, c.country].filter(Boolean).join(", ") || null },
              { label: "Owner", value: <EntityName kind="member" id={c.owner_id} /> },
              { label: "Added", value: relative(c.created_at) },
            ]}
          />
          {c.tags.length ? <div className="mt-4 flex flex-wrap gap-1.5">{c.tags.map((t) => <Badge key={t}>{t}</Badge>)}</div> : null}
          {c.description ? <p className="mt-4 border-t border-line pt-4 text-sm whitespace-pre-line text-ink-2">{c.description}</p> : null}
        </>
      )}
      tabs={(c) => [
        { value: "timeline", label: "Timeline", content: <Timeline entity="contacts" id={c.id} /> },
        { value: "deals", label: "Deals", content: <DealsPanel filter={{ contact_id: c.id }} /> },
        { value: "tasks", label: "Tasks", content: <TasksPanel field="contact_id" id={c.id} /> },
        { value: "notes", label: "Notes", content: <NotesPanel field="contact_id" id={c.id} /> },
        { value: "emails", label: "Emails", content: <RecordEmailsPanel field="contact_id" id={c.id} /> },
        { value: "memory", label: "AI memory", content: <RecordMemoryPanel field="contact_id" id={c.id} /> },
      ]}
    />
  );
}
