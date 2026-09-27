import type { ColumnDef } from "@tanstack/react-table";
import { Plus, Search } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { Button, EmptyState, ErrorState, Input, Select } from "@/components/ui/primitives";
import type { resource } from "@/hooks/resources";
import { PageHeader } from "@/layouts/AppShell";
import { describeError } from "@/services/api";
import { useCan } from "@/stores/auth";
import { DataTable } from "./DataTable";
import { EntityForm, type FieldSpec } from "./EntityForm";

export interface FilterSpec {
  name: string;
  label: string;
  options: { value: string; label: string }[];
}

type Resource<T extends { id: string }> = ReturnType<typeof resource<T>>;

/**
 * A module's list screen: search, filters, server-side sort + pagination, and
 * a create sheet. State lives in the URL so views can be shared and survive reloads.
 */
export function ListPage<T extends { id: string }>({
  res,
  title,
  description,
  noun,
  columns,
  fields,
  filters = [],
  basePath,
  emptyIcon,
  emptyBody,
  createDefaults,
  headerExtra,
  toInput,
}: {
  res: Resource<T>;
  title: string;
  description: string;
  noun: string;
  columns: ColumnDef<T, any>[];
  fields: FieldSpec[];
  filters?: FilterSpec[];
  basePath: string;
  emptyIcon: ReactNode;
  emptyBody: string;
  createDefaults?: Record<string, unknown>;
  headerExtra?: ReactNode;
  toInput?: (v: Record<string, unknown>) => Record<string, unknown>;
}) {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const canWrite = useCan("crm:write");
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState(params.get("q") ?? "");

  const page = Number(params.get("page") ?? 1);
  const sort = params.get("sort") ?? undefined;
  const filterValues = Object.fromEntries(filters.map((f) => [f.name, params.get(f.name) ?? ""]));

  const update = (patch: Record<string, string | undefined>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    if (!("page" in patch)) next.delete("page");
    setParams(next, { replace: true });
  };

  // Debounce the search box into the URL.
  useEffect(() => {
    const t = setTimeout(() => {
      if ((params.get("q") ?? "") !== search) update({ q: search || undefined });
    }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  // Empty filters are left out, so the default view shares its cache entry with sidebar prefetching.
  const activeFilters = Object.fromEntries(Object.entries(filterValues).filter(([, v]) => v));
  const list = res.useList({ page, page_size: 25, sort, q: params.get("q") || undefined, ...activeFilters });
  const create = res.useCreate();
  const filtered = Boolean(params.get("q")) || Object.values(filterValues).some(Boolean);

  return (
    <>
      <PageHeader
        title={title}
        description={description}
        actions={
          <>
            {headerExtra}
            {canWrite ? (
              <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>
                New {noun.toLowerCase()}
              </Button>
            ) : null}
          </>
        }
      />

      <div className="rise mb-3 flex flex-wrap items-center gap-2" style={{ animationDelay: "40ms" }}>
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={`Search ${title.toLowerCase()}`}
            aria-label={`Search ${title.toLowerCase()}`}
            className="pl-9"
          />
        </div>
        {filters.map((f) => (
          <Select
            key={f.name}
            aria-label={f.label}
            value={filterValues[f.name]}
            onChange={(e) => update({ [f.name]: e.target.value || undefined })}
            className="w-auto min-w-40"
          >
            <option value="">{f.label}: all</option>
            {f.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        ))}
      </div>

      <div className="rise" style={{ animationDelay: "80ms" }}>
        {list.error ? (
          <div className="glass-dense rounded-[var(--radius-card)]">
            <ErrorState message={describeError(list.error)} onRetry={() => list.refetch()} />
          </div>
        ) : (
          <DataTable
            columns={columns}
            rows={list.data?.items}
            total={list.data?.total ?? 0}
            page={page}
            pageSize={25}
            onPageChange={(p) => update({ page: String(p) })}
            sort={sort}
            onSortChange={(s) => update({ sort: s })}
            loading={list.isLoading}
            onRowClick={(row) => navigate(`${basePath}/${row.id}`)}
            empty={
              filtered ? (
                <EmptyState title="No matches" body="Try a different search or clear the filters." />
              ) : (
                <EmptyState
                  icon={emptyIcon}
                  title={`No ${title.toLowerCase()} yet`}
                  body={emptyBody}
                  action={canWrite ? <Button variant="primary" onClick={() => setCreating(true)}>New {noun.toLowerCase()}</Button> : undefined}
                />
              )
            }
          />
        )}
      </div>

      <EntityForm
        open={creating}
        onOpenChange={setCreating}
        title={`New ${noun.toLowerCase()}`}
        fields={fields}
        initial={undefined}
        submitLabel={`Create ${noun.toLowerCase()}`}
        saving={create.isPending}
        onSubmit={async (values) => {
          const row = await create.mutateAsync({ ...createDefaults, ...(toInput ? toInput(values) : values) } as never);
          navigate(`${basePath}/${row.id}`);
        }}
      />
    </>
  );
}
