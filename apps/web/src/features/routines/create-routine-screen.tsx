"use client";

import { useRoutine, useRoutinesLoading } from "@/data/store";
import { PageHeader } from "@/features/shell/page-header";
import { RoutineForm } from "./routine-form";

/** /routines/new — a job a bot repeats: who runs it, what to do and when. */
export function CreateRoutineScreen() {
  return (
    <div className="flex h-full flex-col">
      <PageHeader title="New routine" />
      <div className="flex-1 overflow-y-auto">
        <RoutineForm />
      </div>
    </div>
  );
}

/** /routines/[routineId]/edit — the same form, filled in. */
export function EditRoutineScreen({ routineId }: { routineId: string }) {
  const routine = useRoutine(routineId);
  const loading = useRoutinesLoading();
  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Edit routine" />
      <div className="flex-1 overflow-y-auto">
        {routine ? (
          // Keyed by id: the form's fields start from this routine.
          <RoutineForm key={routine.id} routine={routine} />
        ) : (
          <p className="p-8 text-center text-sm text-muted-foreground">{loading ? "Loading…" : "This routine doesn't exist."}</p>
        )}
      </div>
    </div>
  );
}
