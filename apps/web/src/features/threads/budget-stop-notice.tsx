import Link from "next/link";
import { WalletCards } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useBot } from "@/data/store";
import type { Message } from "@/data/types";
import { EditBotDialog } from "@/features/bots/edit-bot-dialog";

/**
 * A reply that didn't happen because the bot (or the whole org) reached its monthly budget.
 * Says which, and offers the two ways on: raise the bot's budget, or look at Usage & budgets.
 */
export function BudgetStopNotice({ message }: { message: Message }) {
  const bot = useBot(message.author.type === "bot" ? message.author.id : undefined);

  return (
    <Alert className="max-w-[560px]">
      <WalletCards />
      <AlertTitle>Out of budget for this month</AlertTitle>
      <AlertDescription>
        <p>{message.error}</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {bot && <EditBotDialog bot={bot} />}
          <Button asChild variant="ghost" size="sm">
            <Link href="/settings/usage">Usage &amp; budgets</Link>
          </Button>
        </div>
      </AlertDescription>
    </Alert>
  );
}
