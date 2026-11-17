import { toolArguments } from "@/lib/mcp-review";

/** A tool's arguments, as its JSON schema describes them: what the model will be asked to fill in. */
export function McpToolArguments({ schema, label }: { schema: Record<string, unknown> | null; label: string }) {
  const args = toolArguments(schema);
  return (
    <div className="min-w-0">
      <p className="mb-1 text-xs font-medium text-muted-foreground">{label}</p>
      {args.length === 0 ? (
        <p className="text-sm text-muted-foreground">No arguments.</p>
      ) : (
        <ul className="flex flex-col gap-1 text-sm" aria-label={label}>
          {args.map((arg) => (
            <li key={arg.name} className="break-words">
              <code className="rounded bg-muted px-1 py-0.5 text-xs">{arg.name}</code>{" "}
              <span className="text-xs text-muted-foreground">{arg.type}{arg.required ? ", required" : ""}</span>
              {arg.description && <span className="text-muted-foreground"> · {arg.description}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
