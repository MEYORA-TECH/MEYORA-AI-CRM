import * as Tabs from "@radix-ui/react-tabs";
import { ArrowLeft, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAiUi, type PageContext } from "@/ai/store";
import { ConfirmDialog, DropdownMenu, MenuItem } from "@/components/ui/overlay";
import { Button, Card, ErrorState, IconButton, Skeleton } from "@/components/ui/primitives";
import { cn } from "@/lib/format";
import { describeError } from "@/services/api";
import { useCan } from "@/stores/auth";
import { EntityForm, type FieldSpec } from "./EntityForm";

export interface RecordTab {
  value: string;
  label: string;
  count?: number;
  content: ReactNode;
}

/** Detail screen skeleton shared by companies, contacts, leads and deals. */
export function RecordPage<T extends Record<string, any>>({
  backTo,
  backLabel,
  noun,
  query,
  title,
  subtitle,
  badges,
  actions,
  summary,
  tabs,
  fields,
  onSave,
  saving,
  onDelete,
  deleting,
  aiContext,
}: {
  backTo: string;
  backLabel: string;
  noun: string;
  query: { data?: T; isLoading: boolean; error: unknown; refetch: () => unknown };
  title: (row: T) => ReactNode;
  subtitle?: (row: T) => ReactNode;
  badges?: (row: T) => ReactNode;
  actions?: (row: T) => ReactNode;
  summary: (row: T) => ReactNode;
  tabs: (row: T) => RecordTab[];
  fields: FieldSpec[];
  onSave: (values: Record<string, unknown>) => Promise<unknown>;
  saving?: boolean;
  onDelete: () => Promise<unknown>;
  deleting?: boolean;
  /** Tells the assistant which record is on screen. */
  aiContext?: { type: PageContext["type"]; name: (row: T) => string };
}) {
  const navigate = useNavigate();
  const canWrite = useCan("crm:write");
  const canDelete = useCan("crm:delete");
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const row = query.data;
  const setAiPage = useAiUi((s) => s.setPage);
  const aiName = row && aiContext ? aiContext.name(row) : null;
  useEffect(() => {
    if (!row || !aiContext || !aiName) return;
    setAiPage({ type: aiContext.type, id: row.id as string, name: aiName });
    return () => setAiPage(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [row?.id, aiName]);

  if (query.error) {
    return (
      <Card className="mt-6">
        <ErrorState message={describeError(query.error)} onRetry={() => query.refetch()} />
        <div className="pb-8 text-center"><Link to={backTo} className="text-sm font-semibold text-jade">Back to {backLabel}</Link></div>
      </Card>
    );
  }

  return (
    <div className="rise">
      <Link to={backTo} className="focus-ring mb-3 inline-flex items-center gap-1.5 rounded-lg text-sm font-semibold text-ink-3 hover:text-ink">
        <ArrowLeft className="size-4" /> {backLabel}
      </Link>

      {!row ? (
        <div className="space-y-4">
          <Skeleton className="h-10 w-72" />
          <Skeleton className="h-64" />
        </div>
      ) : (
        <>
          <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="text-[28px] leading-tight font-extrabold tracking-[-0.03em] md:text-[32px]">{title(row)}</h1>
                {badges?.(row)}
              </div>
              {subtitle ? <p className="mt-1 text-sm text-ink-2">{subtitle(row)}</p> : null}
            </div>
            <div className="flex items-center gap-2">
              {actions?.(row)}
              {canWrite ? <Button icon={<Pencil className="size-4" />} onClick={() => setEditing(true)}>Edit</Button> : null}
              {canDelete ? (
                <DropdownMenu trigger={<IconButton label="More actions" className="glass-dense"><MoreHorizontal className="size-4" /></IconButton>}>
                  <MenuItem danger icon={<Trash2 className="size-4" />} onSelect={() => setConfirming(true)}>Delete {noun.toLowerCase()}</MenuItem>
                </DropdownMenu>
              ) : null}
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
            <div className="flex h-fit flex-col gap-4">
              <Card className="p-5">{summary(row)}</Card>
              <CustomFields values={row.custom_fields as Record<string, unknown> | undefined} />
            </div>
            <RecordTabs tabs={tabs(row)} />
          </div>

          <EntityForm
            open={editing}
            onOpenChange={setEditing}
            title={`Edit ${noun.toLowerCase()}`}
            fields={fields}
            initial={row}
            submitLabel="Save changes"
            saving={saving}
            onSubmit={onSave}
          />
          <ConfirmDialog
            open={confirming}
            onOpenChange={setConfirming}
            title={`Delete this ${noun.toLowerCase()}?`}
            description="It will be removed from lists and search. Linked activities and notes stay in the history."
            confirmLabel={`Delete ${noun.toLowerCase()}`}
            loading={deleting}
            onConfirm={async () => {
              await onDelete();
              navigate(backTo);
            }}
          />
        </>
      )}
    </div>
  );
}

function RecordTabs({ tabs }: { tabs: RecordTab[] }) {
  const [value, setValue] = useState(tabs[0]?.value);
  return (
    <Tabs.Root value={value} onValueChange={setValue} className="min-w-0">
      <Tabs.List aria-label="Record sections" className="glass-soft mb-3 inline-flex max-w-full gap-1 overflow-x-auto rounded-full p-1">
        {tabs.map((t) => (
          <Tabs.Trigger
            key={t.value}
            value={t.value}
            className={cn(
              "focus-ring flex h-8 items-center gap-1.5 rounded-full px-3.5 text-[13px] font-semibold whitespace-nowrap text-ink-2 transition",
              "hover:text-ink data-[state=active]:bg-[var(--ink)] data-[state=active]:text-[var(--canvas)]",
            )}
          >
            {t.label}
            {t.count !== undefined ? <span className="num text-[11px] opacity-60">{t.count}</span> : null}
          </Tabs.Trigger>
        ))}
      </Tabs.List>
      {tabs.map((t) => (
        <Tabs.Content key={t.value} value={t.value} className="focus:outline-none">
          <Card className="overflow-hidden">{t.content}</Card>
        </Tabs.Content>
      ))}
    </Tabs.Root>
  );
}

/** Extra fields kept with the record (e.g. from a spreadsheet import). */
function CustomFields({ values }: { values?: Record<string, unknown> }) {
  const items = Object.entries(values ?? {}).filter(([, v]) => v !== null && v !== undefined && v !== "");
  if (!items.length) return null;
  return (
    <Card className="p-5">
      <h2 className="mb-3 text-[13px] font-semibold tracking-wide text-ink-3 uppercase">Details</h2>
      <Facts
        items={items.map(([label, v]) => {
          const text = typeof v === "object" ? JSON.stringify(v) : String(v);
          return {
            label,
            value: /^https?:\/\//.test(text) ? (
              <a href={text} target="_blank" rel="noopener noreferrer" className="text-jade hover:underline">
                {text.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")}
              </a>
            ) : text,
          };
        })}
      />
    </Card>
  );
}

/** Label/value list for the summary card. */
export function Facts({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <dl className="divide-y divide-[var(--line)]">
      {items.map((i) => (
        <div key={i.label} className="flex items-start justify-between gap-4 py-2.5 first:pt-0 last:pb-0">
          <dt className="text-[13px] text-ink-3">{i.label}</dt>
          <dd className="max-w-[60%] text-right text-sm font-medium break-words text-ink">{i.value ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}
