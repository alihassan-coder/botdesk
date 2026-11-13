import { CreditCard, Eye, FilePen, KeyRound, NotebookPen, Send, TriangleAlert, type LucideIcon } from "lucide-react";
import type { RiskClass } from "@/data/types";

/** Plain-language meaning of each risk class (GLOSSARY.md → Risk class), shown on approval cards. */
export const RISK: Record<RiskClass, { label: string; icon: LucideIcon }> = {
  read: { label: "Reads your data", icon: Eye },
  "write-internal": { label: "Keeps internal notes", icon: NotebookPen },
  "write-external": { label: "Changes things in your apps", icon: FilePen },
  "external-send": { label: "Sends outside your org", icon: Send },
  spend: { label: "Spends money", icon: CreditCard },
  destructive: { label: "Can't be undone", icon: TriangleAlert },
  credential: { label: "Needs a login", icon: KeyRound },
};
