import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, KeyRound, LockKeyhole, Trash2 } from "@/components/icons";
import { useState } from "react";
import { toast } from "sonner";

import { EntityName } from "@/components/data/EntityPicker";
import { ConfirmDialog } from "@/components/ui/overlay";
import { Badge, Button, Card, CardHeader, ErrorState, Input, Skeleton } from "@/components/ui/primitives";
import { relative } from "@/lib/format";
import { api, describeError } from "@/services/api";
import type { components } from "@/types/api";

type ApiKey = components["schemas"]["ApiKeyOut"];
const KEYS = ["/organization/api-keys"];

/** Settings → API keys (owner only). Keys go in once; afterwards only their last four characters are shown. */
export function ApiKeysTab() {
  const keys = useQuery({ queryKey: KEYS, queryFn: () => api.get<ApiKey[]>("/organization/api-keys") });

  if (keys.error) return <ErrorState message={describeError(keys.error)} onRetry={() => keys.refetch()} />;
  return (
    <Card>
      <CardHeader
        title="API keys"
        subtitle="Keys your workspace uses for the assistant and web search. Your own key is used first; without one, Meyora's shared key is used when available."
      />
      <div className="mx-5 mb-4 flex items-start gap-2.5 rounded-2xl bg-glass-2 px-3.5 py-3 text-[13px] text-ink-2">
        <LockKeyhole className="mt-0.5 size-4 shrink-0 text-jade" />
        <p>
          Keys are checked with the provider, then stored encrypted. Nobody can view a saved key again, including you and the
          assistant. Only the workspace owner can see this page.
        </p>
      </div>
      <ul className="divide-y divide-[var(--line)] border-t border-line">
        {keys.isLoading
          ? Array.from({ length: 4 }, (_, i) => <li key={i} className="p-5"><Skeleton className="h-12" /></li>)
          : keys.data?.map((k) => <KeyRow key={k.provider} item={k} />)}
      </ul>
    </Card>
  );
}

function KeyRow({ item }: { item: ApiKey }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [removing, setRemoving] = useState(false);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: KEYS });
    qc.invalidateQueries({ queryKey: ["ai", "status"] });
    qc.invalidateQueries({ queryKey: ["web", "status"] });
  };
  const save = useMutation({
    mutationFn: () => api.put<ApiKey>(`/organization/api-keys/${item.provider}`, { value }),
    onSuccess: (saved) => {
      refresh();
      setEditing(false);
      setValue("");
      toast.success(saved.verified_at ? `${item.label} key saved and working` : `${item.label} key saved`);
    },
  });
  const remove = useMutation({
    mutationFn: () => api.delete(`/organization/api-keys/${item.provider}`),
    onSuccess: () => {
      refresh();
      toast.success(`${item.label} key removed`);
    },
    onError: (e) => toast.error(describeError(e)),
  });

  const own = item.source === "organization";
  return (
    <li className="px-5 py-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-glass-2 text-ink-2">
          <KeyRound className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 font-semibold">
            {item.label}
            {own ? (
              <Badge tint="emerald">Your key ••••{item.last4}</Badge>
            ) : item.source === "server" ? (
              <Badge tint="sky">Using Meyora's shared key</Badge>
            ) : (
              <Badge tint="slate">Not set</Badge>
            )}
          </p>
          <p className="text-[13px] text-ink-3">{item.used_for}</p>
          {own && item.updated_at ? (
            <p className="mt-0.5 text-xs text-ink-3">
              Added {relative(item.updated_at)} by <EntityName kind="member" id={item.updated_by_id} />
              {item.verified_at ? " · checked with the provider" : " · couldn't be checked, used as entered"}
            </p>
          ) : null}
        </div>
        {!editing ? (
          <div className="flex items-center gap-2">
            {own ? (
              <Button size="sm" variant="ghost" icon={<Trash2 className="size-3.5" />} onClick={() => setRemoving(true)}>
                Remove
              </Button>
            ) : null}
            <Button size="sm" onClick={() => setEditing(true)}>{own ? "Replace key" : "Add key"}</Button>
          </div>
        ) : null}
      </div>

      {editing ? (
        <form
          className="mt-3 flex flex-col gap-2 sm:ml-13"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              type="password"
              autoComplete="off"
              spellCheck={false}
              autoFocus
              aria-label={`${item.label} API key`}
              placeholder={`Paste your ${item.label} key`}
              value={value}
              onChange={(e) => {
                setValue(e.target.value);
                save.reset();
              }}
              className="font-mono text-[13px]"
            />
            <div className="flex shrink-0 gap-2">
              <Button type="button" variant="ghost" onClick={() => { setEditing(false); setValue(""); save.reset(); }}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" loading={save.isPending} disabled={value.trim().length < 16}>
                Check and save
              </Button>
            </div>
          </div>
          {save.error ? <p className="text-xs font-medium text-danger">{describeError(save.error)}</p> : null}
          <a href={item.get_key_url} target="_blank" rel="noopener noreferrer"
            className="inline-flex w-fit items-center gap-1 text-xs font-semibold text-jade hover:underline">
            Get a {item.label} key <ExternalLink className="size-3" />
          </a>
        </form>
      ) : null}

      <ConfirmDialog
        open={removing}
        onOpenChange={setRemoving}
        title={`Remove your ${item.label} key?`}
        description={
          item.source === "organization"
            ? "The workspace goes back to Meyora's shared key if there is one; otherwise these features stop until a key is added."
            : ""
        }
        confirmLabel="Remove key"
        loading={remove.isPending}
        onConfirm={async () => {
          await remove.mutateAsync();
          setRemoving(false);
        }}
      />
    </li>
  );
}
