import { DndContext, PointerSensor, KeyboardSensor, useDraggable, useDroppable, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { createColumnHelper } from "@tanstack/react-table";
import { CalendarDays, Handshake, KanbanSquare, List, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { EntityForm } from "@/components/data/EntityForm";
import { EntityName } from "@/components/data/EntityPicker";
import { ListPage } from "@/components/data/ListPage";
import { Facts, RecordPage } from "@/components/data/RecordPage";
import { LogActivityButton, NotesPanel, TasksPanel } from "@/components/data/Related";
import { RecordMemoryPanel } from "@/ai/memories";
import { Timeline } from "@/components/data/Timeline";
import { Badge, Button, EmptyState, ErrorState, Skeleton, tintBg } from "@/components/ui/primitives";
import { deals, useBoard, useMoveDeal, usePipelines } from "@/hooks/resources";
import { PageHeader } from "@/layouts/AppShell";
import { cn, date, money, relative } from "@/lib/format";
import { DEAL_STATUS } from "@/lib/status";
import { describeError } from "@/services/api";
import { useCan, useCurrency } from "@/stores/auth";
import type { BoardColumn, Deal } from "@/types";
import { dealFields } from "./fields";

function useStageOptions() {
  const pipelines = usePipelines();
  const pipeline = pipelines.data?.[0];
  const stages = pipeline?.stages ?? [];
  return {
    pipeline,
    stages,
    options: stages.map((s) => ({ value: s.id, label: s.name })),
    nameOf: (id: string) => stages.find((s) => s.id === id)?.name ?? "—",
    colorOf: (id: string) => stages.find((s) => s.id === id)?.color ?? "slate",
  };
}

function ViewToggle({ view }: { view: "board" | "list" }) {
  const [params, setParams] = useSearchParams();
  const set = (v: string) => {
    const next = new URLSearchParams(params);
    next.set("view", v);
    setParams(next, { replace: true });
  };
  const btn = (v: "board" | "list", Icon: typeof List, text: string) => (
    <button
      onClick={() => set(v)}
      aria-pressed={view === v}
      className={cn(
        "focus-ring flex h-8 items-center gap-1.5 rounded-full px-3 text-[13px] font-semibold text-ink-2 transition",
        view === v && "bg-[var(--ink)] text-[var(--canvas)]",
      )}
    >
      <Icon className="size-4" /> {text}
    </button>
  );
  return (
    <div className="glass-soft flex gap-1 rounded-full p-1" role="group" aria-label="View">
      {btn("board", KanbanSquare, "Board")}
      {btn("list", List, "List")}
    </div>
  );
}

/* ---------------- Board ---------------- */

function DealCard({ deal, dragging }: { deal: Deal; dragging?: boolean }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: deal.id, data: { stageId: deal.stage_id } });
  const overdue = deal.status === "open" && deal.expected_close_date && new Date(deal.expected_close_date) < new Date(new Date().toDateString());
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Translate.toString(transform) }}
      className={cn("touch-none", isDragging && "relative z-20")}
      {...attributes}
      {...listeners}
    >
      <Link
        to={`/deals/${deal.id}`}
        draggable={false}
        className={cn(
          "glass-dense block rounded-2xl p-3.5 transition-shadow hover:shadow-[var(--glass-shadow)]",
          (isDragging || dragging) && "rotate-[1.5deg] shadow-[var(--glass-shadow)]",
        )}
      >
        <p className="text-sm leading-snug font-semibold">{deal.name}</p>
        <p className="mt-0.5 truncate text-xs text-ink-3">{deal.company?.name ?? "No company"}</p>
        <div className="mt-3 flex items-center justify-between gap-2">
          <span className="num text-[15px] font-bold tracking-tight">{money(deal.amount, deal.currency, { compact: true })}</span>
          <span className={cn("inline-flex items-center gap-1 text-[11px]", overdue ? "font-semibold text-danger" : "text-ink-3")}>
            <CalendarDays className="size-3" />
            {deal.expected_close_date ? date(deal.expected_close_date) : "No date"}
          </span>
        </div>
        <div className="mt-2.5 h-1 overflow-hidden rounded-full bg-[var(--line-strong)]">
          <div className="h-full rounded-full bg-jade" style={{ width: `${deal.probability}%` }} />
        </div>
      </Link>
    </div>
  );
}

function StageColumn({ column, currency }: { column: BoardColumn; currency: string }) {
  const { setNodeRef, isOver } = useDroppable({ id: column.stage_id });
  return (
    <section
      ref={setNodeRef}
      aria-label={`${column.name} stage`}
      className={cn(
        "glass-soft flex w-[272px] shrink-0 flex-col rounded-[22px] p-2 transition-colors",
        isOver && "ring-2 ring-[var(--jade)]",
      )}
    >
      <header className={cn("mb-2 rounded-2xl px-3 py-2.5", tintBg(column.color))}>
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-bold">{column.name}</h2>
          <span className="num text-xs font-semibold opacity-75">{column.count}</span>
        </div>
        <p className="num mt-0.5 text-xs font-semibold opacity-80">{money(column.total_amount, currency, { compact: true })}</p>
      </header>
      <div className="flex min-h-24 flex-col gap-2">
        {column.deals.map((d) => <DealCard key={d.id} deal={d} />)}
        {column.count > column.deals.length ? (
          <p className="px-2 py-1 text-center text-xs text-ink-3">+{column.count - column.deals.length} more in list view</p>
        ) : null}
      </div>
    </section>
  );
}

function Board({ pipelineId }: { pipelineId?: string }) {
  const board = useBoard(pipelineId);
  const move = useMoveDeal(pipelineId);
  const canWrite = useCan("crm:write");
  const currency = useCurrency();
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor),
  );

  const onDragEnd = (e: DragEndEvent) => {
    const toStage = e.over?.id as string | undefined;
    const fromStage = e.active.data.current?.stageId as string | undefined;
    if (!toStage || toStage === fromStage || !canWrite) return;
    move.mutate({ dealId: String(e.active.id), stageId: toStage });
  };

  if (board.error) return <ErrorState message={describeError(board.error)} onRetry={() => board.refetch()} />;
  if (!board.data) {
    return <div className="flex gap-3 overflow-hidden">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-96 w-[272px] shrink-0" />)}</div>;
  }
  return (
    <DndContext sensors={sensors} onDragEnd={onDragEnd}>
      <div className="-mx-4 flex gap-3 overflow-x-auto px-4 pb-4 md:mx-0 md:px-0">
        {board.data.columns.map((c) => <StageColumn key={c.stage_id} column={c} currency={currency} />)}
      </div>
    </DndContext>
  );
}

/* ---------------- List ---------------- */

const col = createColumnHelper<Deal>();

function useDealColumns() {
  const { nameOf, colorOf } = useStageOptions();
  return useMemo(
    () => [
      col.accessor("name", {
        header: "Deal",
        meta: { sortKey: "name" },
        cell: (c) => (
          <div className="min-w-0">
            <p className="truncate font-semibold">{c.getValue()}</p>
            <p className="truncate text-xs text-ink-3">{c.row.original.company?.name ?? ""}</p>
          </div>
        ),
      }),
      col.accessor("stage_id", {
        header: "Stage",
        cell: (c) => <Badge tint={colorOf(c.getValue()) as never}>{nameOf(c.getValue())}</Badge>,
      }),
      col.accessor("amount", {
        header: "Amount",
        meta: { sortKey: "amount", align: "right" },
        cell: (c) => <span className="font-semibold">{money(c.getValue(), c.row.original.currency)}</span>,
      }),
      col.accessor("probability", { header: "Prob.", meta: { sortKey: "probability", align: "right" }, cell: (c) => `${c.getValue()}%` }),
      col.accessor("expected_close_date", { header: "Close date", meta: { sortKey: "expected_close_date" }, cell: (c) => date(c.getValue()) }),
      col.accessor("owner_id", { header: "Owner", cell: (c) => <EntityName kind="member" id={c.getValue()} /> }),
    ],
    [nameOf, colorOf],
  );
}

export function DealsPage() {
  const [params] = useSearchParams();
  const view = params.get("view") === "list" ? "list" : "board";
  const { pipeline, options } = useStageOptions();
  const columns = useDealColumns();
  const fields = dealFields(options);
  const canWrite = useCan("crm:write");
  const create = deals.useCreate();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);

  if (view === "list") {
    return (
      <ListPage
        res={deals}
        title="Deals"
        description="Your pipeline as a sortable list."
        noun="Deal"
        columns={columns}
        fields={fields}
        filters={[{ name: "status", label: "Status", options: Object.entries(DEAL_STATUS).map(([value, v]) => ({ value, label: v.label })) }]}
        basePath="/deals"
        emptyIcon={<Handshake className="size-5" />}
        emptyBody="Create a deal, or convert a qualified lead."
        headerExtra={<ViewToggle view="list" />}
      />
    );
  }

  return (
    <>
      <PageHeader
        title="Deals"
        description={pipeline ? `${pipeline.name} · drag a card to move it to another stage.` : "Your pipeline"}
        actions={
          <>
            <ViewToggle view="board" />
            {canWrite ? <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>New deal</Button> : null}
          </>
        }
      />
      <div className="rise" style={{ animationDelay: "60ms" }}>
        {pipeline ? <Board pipelineId={pipeline.id} /> : <EmptyState title="No pipeline" body="Create a pipeline in Settings to start tracking deals." />}
      </div>
      <EntityForm
        open={creating}
        onOpenChange={setCreating}
        title="New deal"
        fields={fields}
        submitLabel="Create deal"
        saving={create.isPending}
        onSubmit={async (v) => {
          const row = await create.mutateAsync(v as never);
          navigate(`/deals/${row.id}`);
        }}
      />
    </>
  );
}

/* ---------------- Detail ---------------- */

export function DealDetailPage() {
  const { id = "" } = useParams();
  const query = deals.useOne(id);
  const update = deals.useUpdate();
  const remove = deals.useDelete();
  const canWrite = useCan("crm:write");
  const { stages, options, nameOf } = useStageOptions();

  return (
    <RecordPage<Deal>
      backTo="/deals"
      backLabel="Deals"
      noun="Deal"
      query={query}
      aiContext={{ type: "deal", name: (d) => d.name }}
      title={(d) => d.name}
      subtitle={(d) => (d.company ? <Link className="font-semibold text-jade hover:underline" to={`/companies/${d.company.id}`}>{d.company.name}</Link> : undefined)}
      badges={(d) => <Badge tint={DEAL_STATUS[d.status].tint}>{DEAL_STATUS[d.status].label}</Badge>}
      actions={(d) => <LogActivityButton link={{ deal_id: d.id, ...(d.company_id ? { company_id: d.company_id } : {}) }} />}
      fields={dealFields(options)}
      saving={update.isPending}
      onSave={(input) => update.mutateAsync({ id, input })}
      onDelete={() => remove.mutateAsync(id)}
      deleting={remove.isPending}
      summary={(d) => (
        <>
          <p className="num text-[34px] leading-none font-extrabold tracking-[-0.04em]">{money(d.amount, d.currency)}</p>
          <p className="mt-1.5 text-xs text-ink-3">{d.probability}% probability · weighted {money((d.amount * d.probability) / 100, d.currency)}</p>

          {/* Stage stepper: the pipeline as a row of segments, clickable to move. */}
          <div className="mt-5">
            <p className="mb-2 text-[13px] text-ink-3">Stage · <span className="font-semibold text-ink">{nameOf(d.stage_id)}</span></p>
            <div className="flex gap-1" role="group" aria-label="Move to stage">
              {stages.map((s) => {
                const current = s.id === d.stage_id;
                const idx = stages.findIndex((x) => x.id === d.stage_id);
                const passed = stages.indexOf(s) <= idx && s.kind === "open";
                return (
                  <button
                    key={s.id}
                    disabled={!canWrite || current}
                    title={s.name}
                    aria-label={`Move to ${s.name}`}
                    aria-current={current}
                    onClick={() => update.mutate({ id: d.id, input: { stage_id: s.id } })}
                    className={cn(
                      "focus-ring h-2.5 flex-1 rounded-full transition disabled:cursor-default",
                      current ? (s.kind === "lost" ? "bg-danger" : "bg-jade") : passed ? "bg-jade/40" : "bg-[var(--line-strong)] hover:bg-jade/30",
                    )}
                  />
                );
              })}
            </div>
          </div>

          <div className="mt-5">
            <Facts
              items={[
                { label: "Expected close", value: date(d.expected_close_date) },
                { label: "Contact", value: d.contact_id ? <Link className="text-jade hover:underline" to={`/contacts/${d.contact_id}`}><EntityName kind="contact" id={d.contact_id} /></Link> : null },
                { label: "Owner", value: <EntityName kind="member" id={d.owner_id} /> },
                { label: "Source", value: d.source },
                { label: "Closed", value: d.closed_at ? relative(d.closed_at) : null },
                { label: "Created", value: relative(d.created_at) },
              ]}
            />
          </div>
          {d.tags.length ? <div className="mt-4 flex flex-wrap gap-1.5">{d.tags.map((t) => <Badge key={t}>{t}</Badge>)}</div> : null}
          {d.description ? <p className="mt-4 border-t border-line pt-4 text-sm whitespace-pre-line text-ink-2">{d.description}</p> : null}
        </>
      )}
      tabs={(d) => [
        { value: "timeline", label: "Timeline", content: <Timeline entity="deals" id={d.id} /> },
        { value: "tasks", label: "Tasks", content: <TasksPanel field="deal_id" id={d.id} /> },
        { value: "notes", label: "Notes", content: <NotesPanel field="deal_id" id={d.id} /> },
        { value: "memory", label: "AI memory", content: <RecordMemoryPanel field="deal_id" id={d.id} /> },
      ]}
    />
  );
}
