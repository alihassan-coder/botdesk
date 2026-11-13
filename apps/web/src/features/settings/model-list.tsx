import { useMemo, useState } from "react";
import { RefreshCw, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { actions, isDemoMode, useModelProblems, useModelProviders, useModels, useModelsLoading } from "@/data/store";
import { formatContextWindow, formatModelPrice, groupModels } from "@/lib/models";

/** Every model the connected providers offer right now, grouped by provider, with search and refresh. */
export function ModelList() {
  const models = useModels();
  const providers = useModelProviders();
  const loading = useModelsLoading();
  const problems = useModelProblems();
  const [query, setQuery] = useState("");
  const groups = useMemo(() => groupModels(models, providers, query), [models, providers, query]);
  const nameOf = (id: string) => providers.find((p) => p.id === id)?.name ?? id;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-2">
        <InputGroup className="flex-1">
          <InputGroupAddon><Search /></InputGroupAddon>
          <InputGroupInput aria-label="Search models" placeholder="Search models" value={query} onChange={(e) => setQuery(e.target.value)} />
        </InputGroup>
        <Button variant="outline" size="sm" disabled={loading || isDemoMode()} onClick={() => void actions.loadModels({ refresh: true })}>
          <RefreshCw className={loading ? "animate-spin" : undefined} /> Refresh
        </Button>
      </div>

      {problems.map((p) => (
        <p key={p.provider} role="alert" className="rounded-xl bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {p.provider ? `${nameOf(p.provider)} didn't send its models. ` : ""}{p.message}
        </p>
      ))}

      {groups.length === 0 ? (
        <p className="rounded-2xl border border-dashed p-6 text-center text-sm text-muted-foreground">
          {loading ? "Asking the providers for their models…" : query ? "No models match that." : "Connect a provider above to see its models."}
        </p>
      ) : (
        groups.map((group) => (
          <section key={group.providerId} aria-label={group.providerName} className="flex flex-col gap-2">
            <h3 className="text-sm font-medium text-muted-foreground">{group.providerName} · {group.models.length}</h3>
            <ul className="flex flex-col divide-y rounded-2xl border">
              {group.models.map((m) => (
                <li key={m.id} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 px-4 py-3">
                  <div className="min-w-40 flex-1">
                    <p className="font-medium">{m.name}</p>
                    <p className="truncate font-mono text-xs text-muted-foreground">{m.id}</p>
                  </div>
                  <p className="text-right text-sm text-muted-foreground tabular-nums">
                    {formatModelPrice(m)}
                    <span className="block text-xs">{formatContextWindow(m)}</span>
                  </p>
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}
