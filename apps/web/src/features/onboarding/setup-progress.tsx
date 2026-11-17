import { cn } from "@/lib/utils";

/** Where you are in setup: one bar per step, filled up to the current one, with its name. */
export function SetupProgress({ steps, current }: { steps: string[]; current: number }) {
  return (
    <nav aria-label="Setup progress" className="flex flex-col gap-3">
      <p className="text-sm text-muted-foreground" aria-live="polite">
        Step {current + 1} of {steps.length}
      </p>
      <ol className="grid gap-2" style={{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }}>
        {steps.map((name, i) => (
          <li key={name} aria-current={i === current ? "step" : undefined} className="flex flex-col gap-2">
            <span className={cn("h-1 rounded-full bg-muted transition-colors duration-300", i <= current && "bg-brand")} />
            <span className={cn("hidden truncate text-xs sm:block", i === current ? "font-medium text-foreground" : "text-muted-foreground")}>{name}</span>
            {/* Phones show only the bars; screen readers still hear each step's name. */}
            <span className="sr-only sm:hidden">{name}</span>
          </li>
        ))}
      </ol>
    </nav>
  );
}
