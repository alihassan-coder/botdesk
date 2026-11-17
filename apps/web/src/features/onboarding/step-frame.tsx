import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";

interface StepFrameProps {
  title: string;
  description: string;
  children: React.ReactNode;
  /** The step's main button: Continue, or Finish on the last one. */
  action: React.ReactNode;
  onSkip: () => void;
  skipLabel?: string;
}

/**
 * One step of first-time setup: what it's for, the step itself, then Skip and the main button.
 * Every step can be skipped; nothing here is needed to start using botdesk.
 */
export function StepFrame({ title, description, children, action, onSkip, skipLabel = "Skip" }: StepFrameProps) {
  const heading = useRef<HTMLHeadingElement>(null);
  // The previous step's button is gone, so keyboard focus would fall to the page: start at the
  // new step's title instead, unless the step already focused a field of its own (autoFocus).
  useEffect(() => {
    if (document.activeElement === document.body) heading.current?.focus();
  }, []);

  return (
    <section aria-labelledby="setup-step-title" className="flex flex-col gap-8 motion-safe:animate-in motion-safe:fade-in motion-safe:duration-300">
      <header className="flex flex-col gap-2">
        <h1 id="setup-step-title" ref={heading} tabIndex={-1} className="outline-none text-2xl font-semibold tracking-tight text-balance sm:text-3xl">{title}</h1>
        <p className="text-pretty text-muted-foreground">{description}</p>
      </header>
      <div className="flex flex-col gap-4">{children}</div>
      <footer className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
        <Button type="button" variant="ghost" onClick={onSkip} className="text-muted-foreground">{skipLabel}</Button>
        {action}
      </footer>
    </section>
  );
}
