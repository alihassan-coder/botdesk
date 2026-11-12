"use client";

import Link from "next/link";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useRoutines } from "@/data/store";
import { PageHeader } from "@/features/shell/page-header";
import { RoutineCard } from "./routine-card";

/** /routines — jobs your bots repeat on a schedule. Switch them on and off, see how they went. */
export function RoutinesScreen() {
  const routines = useRoutines();
  const active = routines.filter((r) => r.enabled).length;

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Routines">
        <Button asChild size="sm">
          <Link href="/routines/new">
            <Plus /> New routine
          </Link>
        </Button>
      </PageHeader>
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-3xl flex-col gap-6 p-4 md:p-8">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Routines</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {active} of {routines.length} running. A bot learns a routine by watching you once, or when you ask in chat.
            </p>
          </div>
          {routines.length === 0 && (
            <p className="rounded-2xl border border-dashed p-6 text-center text-sm text-muted-foreground">
              No routines yet. Ask a bot to do something every week, or create one with New routine.
            </p>
          )}
          {routines.map((r) => (
            <RoutineCard key={r.id} routine={r} />
          ))}
        </div>
      </div>
    </div>
  );
}
