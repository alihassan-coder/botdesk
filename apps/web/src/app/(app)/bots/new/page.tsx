import type { Metadata } from "next";
import { CreateBotScreen } from "@/features/bots/create-bot-screen";

export const metadata: Metadata = { title: "New bot" };

export default function NewBotPage() {
  return <CreateBotScreen />;
}
