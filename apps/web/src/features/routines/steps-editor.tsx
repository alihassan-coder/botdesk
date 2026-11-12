import { Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** An ordered list of steps: type each one, add more, remove any (at least one stays). */
export function StepsEditor({ steps, onChange }: { steps: string[]; onChange: (steps: string[]) => void }) {
  const update = (index: number, value: string) => onChange(steps.map((s, i) => (i === index ? value : s)));
  const remove = (index: number) => onChange(steps.filter((_, i) => i !== index));

  return (
    <div className="flex flex-col gap-2">
      <ol className="flex flex-col gap-2">
        {steps.map((step, i) => (
          <li key={i} className="flex items-center gap-2">
            <span className="w-5 shrink-0 text-right text-sm text-muted-foreground tabular-nums">{i + 1}.</span>
            <Input value={step} onChange={(e) => update(i, e.target.value)} placeholder="e.g. Search Gmail for receipts" aria-label={`Step ${i + 1}`} />
            <Button type="button" variant="ghost" size="icon-sm" onClick={() => remove(i)} disabled={steps.length === 1} aria-label={`Remove step ${i + 1}`}>
              <X />
            </Button>
          </li>
        ))}
      </ol>
      <Button type="button" variant="outline" size="sm" className="ml-7 w-fit" onClick={() => onChange([...steps, ""])}>
        <Plus /> Add step
      </Button>
    </div>
  );
}
