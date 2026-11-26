import type { Metadata } from "next";
import { FilesScreen } from "@/features/files/files-screen";

export const metadata: Metadata = { title: "Files" };

export default function FilesPage() {
  return <FilesScreen />;
}
