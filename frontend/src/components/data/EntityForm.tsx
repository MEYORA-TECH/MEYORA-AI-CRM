import { useEffect, type ReactNode } from "react";
import { Controller, useForm } from "react-hook-form";

import { Button, Field, Input, Select, Textarea } from "@/components/ui/primitives";
import { Sheet } from "@/components/ui/overlay";
import { cn, toLocalInput } from "@/lib/format";
import { EntityPicker, type PickerKind } from "./EntityPicker";

export type FieldSpec = {
  name: string;
  label: string;
  required?: boolean;
  placeholder?: string;
  hint?: string;
  half?: boolean;
} & (
  | { type: "text" | "email" | "url" | "tel" | "textarea" | "tags" | "date" | "datetime" }
  | { type: "number" | "money"; min?: number; max?: number }
  | { type: "select"; options: { value: string; label: string }[]; allowEmpty?: boolean }
  | { type: "ref"; kind: PickerKind }
);

type Values = Record<string, unknown>;

function toFormValue(spec: FieldSpec, value: unknown): unknown {
  if (value === null || value === undefined) return spec.type === "ref" ? null : "";
  if (spec.type === "tags") return (value as string[]).join(", ");
  if (spec.type === "datetime") return toLocalInput(value as string);
  return value;
}

function fromFormValue(spec: FieldSpec, value: unknown): unknown {
  if (spec.type === "ref") return value || null;
  if (spec.type === "tags") {
    return String(value ?? "").split(",").map((t) => t.trim()).filter(Boolean);
  }
  if (value === "" || value === undefined) return null;
  if (spec.type === "number" || spec.type === "money") return Number(value);
  if (spec.type === "datetime") return new Date(String(value)).toISOString();
  return value;
}

/**
 * Create/edit form in a side sheet, driven by field specs. On edit only changed
 * fields are sent, so a PATCH never overwrites what the user didn't touch.
 */
export function EntityForm({
  open,
  onOpenChange,
  title,
  description,
  fields,
  initial,
  submitLabel,
  onSubmit,
  saving,
  footerStart,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  fields: FieldSpec[];
  initial?: Values;
  submitLabel: string;
  onSubmit: (values: Values) => Promise<unknown>;
  saving?: boolean;
  /** Left-aligned footer content, e.g. a destructive action. */
  footerStart?: ReactNode;
}) {
  const defaults = Object.fromEntries(fields.map((f) => [f.name, toFormValue(f, initial?.[f.name])]));
  const form = useForm<Values>({ defaultValues: defaults });

  useEffect(() => {
    if (open) form.reset(defaults);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const submit = form.handleSubmit(async (raw) => {
    const out: Values = {};
    for (const f of fields) {
      const value = fromFormValue(f, raw[f.name]);
      if (initial) {
        const before = fromFormValue(f, toFormValue(f, initial[f.name]));
        if (JSON.stringify(before) !== JSON.stringify(value)) out[f.name] = value;
      } else if (value !== null && !(Array.isArray(value) && value.length === 0)) {
        out[f.name] = value;
      }
    }
    if (initial && Object.keys(out).length === 0) {
      onOpenChange(false);
      return;
    }
    await onSubmit(out);
    onOpenChange(false);
  });

  const formId = `form-${title.replace(/\W+/g, "-").toLowerCase()}`;

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      footer={
        <>
          {footerStart ? <div className="mr-auto">{footerStart}</div> : null}
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="primary" type="submit" form={formId} loading={saving || form.formState.isSubmitting}>
            {submitLabel}
          </Button>
        </>
      }
    >
      <form id={formId} onSubmit={submit} className="grid grid-cols-2 gap-x-4 gap-y-4" noValidate>
        {fields.map((f) => {
          const err = form.formState.errors[f.name]?.message as string | undefined;
          const id = `${formId}-${f.name}`;
          const rules = {
            required: f.required ? `${f.label} is required` : false,
            ...(f.type === "email" ? { pattern: { value: /^\S+@\S+\.\S+$/, message: "Enter a valid email" } } : {}),
            ...(f.type === "number" || f.type === "money"
              ? {
                  min: f.min !== undefined ? { value: f.min, message: `Must be at least ${f.min}` } : undefined,
                  max: f.max !== undefined ? { value: f.max, message: `Must be at most ${f.max}` } : undefined,
                }
              : {}),
          };
          return (
            <Field key={f.name} label={f.required ? `${f.label} *` : f.label} htmlFor={id} error={err} hint={f.hint}
              className={cn(f.half ? "col-span-2 sm:col-span-1" : "col-span-2")}>
              {f.type === "textarea" ? (
                <Textarea id={id} placeholder={f.placeholder} aria-invalid={Boolean(err)} {...form.register(f.name, rules)} />
              ) : f.type === "select" ? (
                <Select id={id} aria-invalid={Boolean(err)} {...form.register(f.name, rules)}>
                  {f.allowEmpty ? <option value="">—</option> : null}
                  {f.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </Select>
              ) : f.type === "ref" ? (
                <Controller
                  control={form.control}
                  name={f.name}
                  rules={{ required: rules.required }}
                  render={({ field }) => (
                    <EntityPicker id={id} kind={f.kind} value={field.value as string | null} onChange={field.onChange} placeholder={f.placeholder} />
                  )}
                />
              ) : (
                <Input
                  id={id}
                  aria-invalid={Boolean(err)}
                  placeholder={f.placeholder ?? (f.type === "tags" ? "Comma-separated, e.g. manufacturing, chennai" : undefined)}
                  type={
                    f.type === "money" || f.type === "number" ? "number"
                    : f.type === "datetime" ? "datetime-local"
                    : f.type === "tags" ? "text"
                    : f.type
                  }
                  step={f.type === "money" ? "0.01" : undefined}
                  inputMode={f.type === "money" || f.type === "number" ? "decimal" : undefined}
                  className={f.type === "money" || f.type === "number" ? "num" : undefined}
                  {...form.register(f.name, rules)}
                />
              )}
            </Field>
          );
        })}
      </form>
    </Sheet>
  );
}
