import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/format";
import { IconButton, Skeleton } from "@/components/ui/primitives";

declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData, TValue> {
    /** API sort key; when set the header becomes a sort toggle. */
    sortKey?: string;
    align?: "left" | "right";
    className?: string;
  }
}

export interface DataTableProps<T> {
  columns: ColumnDef<T, any>[];
  rows: T[] | undefined;
  total: number;
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  sort?: string;
  onSortChange?: (sort: string | undefined) => void;
  loading?: boolean;
  onRowClick?: (row: T) => void;
  empty: ReactNode;
}

export function DataTable<T extends { id: string }>({
  columns, rows, total, page, pageSize, onPageChange, sort, onSortChange, loading, onRowClick, empty,
}: DataTableProps<T>) {
  const table = useReactTable({
    data: rows ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    manualPagination: true,
    getRowId: (r) => r.id,
  });

  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);

  const toggleSort = (key: string) => {
    if (!onSortChange) return;
    if (sort === key) onSortChange(`-${key}`);
    else if (sort === `-${key}`) onSortChange(undefined);
    else onSortChange(key);
  };

  return (
    <div className="glass-dense overflow-hidden rounded-[var(--radius-card)]">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-sm">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b border-line">
                {hg.headers.map((header) => {
                  const meta = header.column.columnDef.meta;
                  const key = meta?.sortKey;
                  const dir = key && sort === key ? "asc" : key && sort === `-${key}` ? "desc" : null;
                  return (
                    <th
                      key={header.id}
                      scope="col"
                      aria-sort={dir === "asc" ? "ascending" : dir === "desc" ? "descending" : undefined}
                      className={cn(
                        "h-11 px-4 text-left text-[12px] font-semibold tracking-wide whitespace-nowrap text-ink-3",
                        meta?.align === "right" && "text-right",
                        meta?.className,
                      )}
                    >
                      {key ? (
                        <button
                          type="button"
                          onClick={() => toggleSort(key)}
                          className={cn("focus-ring inline-flex items-center gap-1 rounded-md hover:text-ink", dir && "text-ink")}
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {dir === "asc" ? <ArrowUp className="size-3.5" /> : dir === "desc" ? <ArrowDown className="size-3.5" /> : null}
                        </button>
                      ) : (
                        flexRender(header.column.columnDef.header, header.getContext())
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {loading && !rows?.length
              ? Array.from({ length: 6 }, (_, i) => (
                  <tr key={i} className="border-b border-line last:border-0">
                    {columns.map((_c, j) => (
                      <td key={j} className="px-4 py-3.5"><Skeleton className="h-4 w-3/4" /></td>
                    ))}
                  </tr>
                ))
              : table.getRowModel().rows.map((row) => (
                  <tr
                    key={row.id}
                    onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                    onKeyDown={onRowClick ? (e) => e.key === "Enter" && onRowClick(row.original) : undefined}
                    tabIndex={onRowClick ? 0 : undefined}
                    className={cn(
                      "border-b border-line transition-colors last:border-0",
                      onRowClick && "focus-ring cursor-pointer hover:bg-[var(--glass-2)]",
                    )}
                  >
                    {row.getVisibleCells().map((cell) => {
                      const meta = cell.column.columnDef.meta;
                      return (
                        <td
                          key={cell.id}
                          className={cn("px-4 py-3 align-middle text-ink", meta?.align === "right" && "num text-right", meta?.className)}
                        >
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      );
                    })}
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
      {!loading && rows && rows.length === 0 ? empty : null}
      {total > 0 ? (
        <div className="flex items-center justify-between border-t border-line px-4 py-2.5 text-xs text-ink-3">
          <span className="num">
            {from}–{to} of {total}
          </span>
          <div className="flex items-center gap-1">
            <IconButton label="Previous page" disabled={page <= 1} onClick={() => onPageChange(page - 1)} className="size-8 disabled:opacity-40">
              <ChevronLeft className="size-4" />
            </IconButton>
            <span className="num px-1">
              {page} / {pages}
            </span>
            <IconButton label="Next page" disabled={page >= pages} onClick={() => onPageChange(page + 1)} className="size-8 disabled:opacity-40">
              <ChevronRight className="size-4" />
            </IconButton>
          </div>
        </div>
      ) : null}
    </div>
  );
}
