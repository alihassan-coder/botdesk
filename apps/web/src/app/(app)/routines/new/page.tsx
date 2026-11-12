import type { Metadata } from "next";
import { CreateRoutineScreen } from "@/features/routines/create-routine-screen";

export const metadata: Metadata = { title: "New routine" };

export default function NewRoutinePage() {
  return <CreateRoutineScreen />;
}
