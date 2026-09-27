import { createColumnHelper } from "@tanstack/react-table";
import { ArrowRightCircle, Magnet } from "@/components/icons";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { EntityName } from "@/components/data/EntityPicker";
import { ListPage } from "@/components/data/ListPage";
import { Facts, RecordPage } from "@/components/data/RecordPage";
import { LogActivityButton, NotesPanel, TasksPanel } from "@/components/data/Related";
import { Timeline } from "@/components/data/Timeline";
import { WebResearchPanel } from "@/research/WebResearchPanel";
import { Modal } from "@/components/ui/overlay";
import { Badge, Button, Field, Input, Select } from "@/components/ui/primitives";
import { leads, useConvertLead, usePipelines } from "@/hooks/resources";
import { cn, relative } from "@/lib/format";
import { LEAD_STATUS, options } from "@/lib/status";
import { useCan } from "@/stores/auth";
import type { Lead } from "@/types";
import { LEAD_FIELDS } from "./fields";

const col = createColumnHelper<Lead>();

function Score({ value }: { value: number }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="h-1.5 w-12 overflow-hidden rounded-full bg-[var(--line-strong)]">
        <span className="block h-full rounded-full bg-jade" style={{ width: `${value}%` }} />
      </span>
      <span className="num text-xs text-ink-2">{value}</span>
    </span>
  );
}

const columns = [
  col.accessor("name", {
    header: "Lead",
    meta: { sortKey: "name" },
    cell: (c) => (
      <div className="min-w-0">
        <p className="truncate font-semibold">{c.getValue()}</p>
        <p className="truncate text-xs text-ink-3">{c.row.original.email ?? c.row.original.phone ?? ""}</p>
      </div>
    ),
  }),
  col.accessor("company_name", { header: "Company", meta: { sortKey: "company_name" }, cell: (c) => c.getValue() ?? "—" }),
  col.accessor("source", { header: "Source", meta: { sortKey: "source" }, cell: (c) => c.getValue() ?? "—" }),
  col.accessor("status", {
    header: "Status",
    meta: { sortKey: "status" },
    cell: (c) => <Badge tint={LEAD_STATUS[c.getValue()].tint}>{LEAD_STATUS[c.getValue()].label}</Badge>,
  }),
  col.accessor("score", { header: "Score", meta: { sortKey: "score" }, cell: (c) => <Score value={c.getValue()} /> }),
  col.accessor("owner_id", { header: "Owner", cell: (c) => <EntityName kind="member" id={c.getValue()} /> }),
  col.accessor("created_at", {
    header: "Created",
    meta: { sortKey: "created_at", align: "right" },
    cell: (c) => <span className="text-ink-3">{relative(c.getValue())}</span>,
  }),
];

export function LeadsPage() {
  return (
    <ListPage
      res={leads}
      title="Leads"
      description="New interest to qualify. Convert a lead to create its company, contact and deal."
      noun="Lead"
      columns={columns}
      fields={LEAD_FIELDS}
      filters={[{ name: "status", label: "Status", options: options(LEAD_STATUS) }]}
      basePath="/leads"
      emptyIcon={<Magnet className="size-5" />}
      emptyBody="Add a lead from a referral, event or enquiry to start qualifying it."
    />
  );
}

function ConvertDialog({ lead, open, onOpenChange }: { lead: Lead; open: boolean; onOpenChange: (o: boolean) => void }) {
  const pipelines = usePipelines();
  const convert = useConvertLead();
  const navigate = useNavigate();
  const pipeline = pipelines.data?.[0];
  const openStages = pipeline?.stages.filter((s) => s.kind === "open") ?? [];
  const [createCompany, setCreateCompany] = useState(Boolean(lead.company_name));
  const [createDeal, setCreateDeal] = useState(true);
  // Imported prospects are named after their company: there's no person to add yet.
  const companyOnly = lead.name.trim().toLowerCase() === (lead.company_name ?? "").trim().toLowerCase();
  const [dealName, setDealName] = useState(`${lead.company_name || lead.name} deal`);
  const [amount, setAmount] = useState("");
  const [stageId, setStageId] = useState("");

  const toggle = (checked: boolean, set: (v: boolean) => void, labelText: string, hint: string, disabled?: boolean) => (
    <label className={cn("flex cursor-pointer items-start gap-3 rounded-2xl border border-line p-3.5", disabled && "cursor-not-allowed opacity-50")}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => set(e.target.checked)} className="mt-0.5 size-4 accent-[var(--jade)]" />
      <span>
        <span className="block text-sm font-semibold">{labelText}</span>
        <span className="block text-xs text-ink-3">{hint}</span>
      </span>
    </label>
  );

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={`Convert ${lead.name}`}
      description="Links or creates the records below and marks this lead as converted."
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            variant="primary"
            loading={convert.isPending}
            onClick={async () => {
              const result = await convert.mutateAsync({
                id: lead.id,
                input: {
                  create_company: createCompany,
                  create_contact: true,
                  create_deal: createDeal,
                  ...(createDeal ? { deal_name: dealName || undefined, deal_amount: amount ? Number(amount) : undefined, stage_id: stageId || undefined } : {}),
                },
              });
              onOpenChange(false);
              if (result.deal_id) navigate(`/deals/${result.deal_id}`);
              else if (result.contact_id) navigate(`/contacts/${result.contact_id}`);
            }}
          >
            Convert lead
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-2.5">
        {toggle(createCompany, setCreateCompany, "Company",
          lead.company_name ? `Link “${lead.company_name}”, or create it if it doesn't exist yet` : "This lead has no company name", !lead.company_name)}
        {companyOnly ? null : toggle(true, () => undefined, "Contact", `Add ${lead.name} as a contact (reuses one with the same email)`, true)}
        {toggle(createDeal, setCreateDeal, "Deal", "Open a deal in your pipeline")}
        {createDeal ? (
          <div className="grid grid-cols-2 gap-3 pt-2">
            <Field label="Deal name" htmlFor="deal-name" className="col-span-2">
              <Input id="deal-name" value={dealName} onChange={(e) => setDealName(e.target.value)} />
            </Field>
            <Field label="Amount (₹)" htmlFor="deal-amount">
              <Input id="deal-amount" type="number" min={0} inputMode="decimal" className="num" value={amount} onChange={(e) => setAmount(e.target.value)} />
            </Field>
            <Field label="Stage" htmlFor="deal-stage">
              <Select id="deal-stage" value={stageId} onChange={(e) => setStageId(e.target.value)}>
                <option value="">{openStages[0]?.name ?? "First stage"}</option>
                {openStages.slice(1).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </Select>
            </Field>
          </div>
        ) : null}
      </div>
    </Modal>
  );
}

export function LeadDetailPage() {
  const { id = "" } = useParams();
  const query = leads.useOne(id);
  const update = leads.useUpdate();
  const remove = leads.useDelete();
  const canWrite = useCan("crm:write");
  const [converting, setConverting] = useState(false);

  return (
    <RecordPage<Lead>
      backTo="/leads"
      backLabel="Leads"
      noun="Lead"
      query={query}
      aiContext={{ type: "lead", name: (l) => l.name }}
      title={(l) => l.name}
      subtitle={(l) => [l.job_title, l.company_name].filter(Boolean).join(" · ") || undefined}
      badges={(l) => <Badge tint={LEAD_STATUS[l.status].tint}>{LEAD_STATUS[l.status].label}</Badge>}
      actions={(l) => (
        <>
          <LogActivityButton link={{ lead_id: l.id }} />
          {canWrite && l.status !== "converted" ? (
            <>
              <Button variant="primary" icon={<ArrowRightCircle className="size-4" />} onClick={() => setConverting(true)}>Convert</Button>
              <ConvertDialog lead={l} open={converting} onOpenChange={setConverting} />
            </>
          ) : null}
        </>
      )}
      fields={query.data?.status === "converted" ? LEAD_FIELDS.filter((f) => f.name !== "status") : LEAD_FIELDS}
      saving={update.isPending}
      onSave={(input) => update.mutateAsync({ id, input })}
      onDelete={() => remove.mutateAsync(id)}
      deleting={remove.isPending}
      summary={(l) => (
        <>
          <Facts
            items={[
              { label: "Email", value: l.email ? <a className="text-jade hover:underline" href={`mailto:${l.email}`}>{l.email}</a> : null },
              { label: "Phone", value: l.phone },
              { label: "Industry", value: l.industry },
              { label: "Source", value: l.source },
              { label: "Score", value: <Score value={l.score} /> },
              { label: "Owner", value: <EntityName kind="member" id={l.owner_id} /> },
              { label: "Created", value: relative(l.created_at) },
            ]}
          />
          {l.status === "converted" ? (
            <div className="mt-4 rounded-2xl bg-jade-soft p-3.5 text-sm">
              <p className="font-semibold text-jade">Converted {relative(l.converted_at)}</p>
              <div className="mt-1.5 flex flex-col gap-1">
                {l.converted_company_id ? <Link className="font-medium hover:underline" to={`/companies/${l.converted_company_id}`}>View company</Link> : null}
                {l.converted_contact_id ? <Link className="font-medium hover:underline" to={`/contacts/${l.converted_contact_id}`}>View contact</Link> : null}
                {l.converted_deal_id ? <Link className="font-medium hover:underline" to={`/deals/${l.converted_deal_id}`}>View deal</Link> : null}
              </div>
            </div>
          ) : null}
          {l.tags.length ? <div className="mt-4 flex flex-wrap gap-1.5">{l.tags.map((t) => <Badge key={t}>{t}</Badge>)}</div> : null}
          {l.description ? <p className="mt-4 border-t border-line pt-4 text-sm whitespace-pre-line text-ink-2">{l.description}</p> : null}
        </>
      )}
      tabs={(l) => [
        { value: "timeline", label: "Timeline", content: <Timeline entity="leads" id={l.id} /> },
        { value: "tasks", label: "Tasks", content: <TasksPanel field="lead_id" id={l.id} /> },
        { value: "notes", label: "Notes", content: <NotesPanel field="lead_id" id={l.id} /> },
        { value: "web", label: "Web research", content: <WebResearchPanel kind="leads" id={l.id} /> },
      ]}
    />
  );
}
