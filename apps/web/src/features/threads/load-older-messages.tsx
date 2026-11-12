import { useTransition } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { actions } from "@/data/store";

/** At the top of a long chat: brings in the page of messages before the oldest one shown. */
export function LoadOlderMessages({ threadId }: { threadId: string }) {
  const [loading, startLoading] = useTransition();

  const loadOlder = () =>
    startLoading(async () => {
      const result = await actions.loadOlderMessages(threadId);
      if (!result.ok) toast.error(result.error);
    });

  return (
    <Button variant="ghost" size="sm" className="mx-auto text-muted-foreground" onClick={loadOlder} disabled={loading}>
      {loading ? "Loading…" : "Show earlier messages"}
    </Button>
  );
}
