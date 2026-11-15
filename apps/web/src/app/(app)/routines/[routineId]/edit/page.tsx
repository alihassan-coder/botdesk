import { Suspense } from "react";
import type { Metadata } from "next";
import { EditRoutineScreen } from "@/features/routines/create-routine-screen";

export const metadata: Metadata = { title: "Edit routine" };

/* Dynamic params resolve inside Suspense (the Next.js 16 pattern, as in /chat/[threadId]). */
export default function EditRoutinePage({ params }: { params: Promise<{ routineId: string }> }) {
  return <Suspense fallback={null}>{params.then(({ routineId }) => <EditRoutineScreen routineId={routineId} />)}</Suspense>;
}
