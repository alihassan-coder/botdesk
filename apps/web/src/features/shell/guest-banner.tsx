import { useRouter } from "next/navigation";
import { Compass } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { actions, useIsGuest } from "@/data/store";

/**
 * Always on top of the app while you explore as a guest, so it's never mistaken for a
 * real account. "Create an account" leaves the demo (its data is thrown away) and opens sign-up.
 */
export function GuestBanner() {
  const isGuest = useIsGuest();
  const router = useRouter();
  if (!isGuest) return null;

  const createAccount = async () => {
    await actions.signOut();
    router.push("/sign-up");
  };

  return (
    <Alert role="status" className="flex items-center gap-3 rounded-none border-x-0 border-t-0 px-4 py-2">
      <Compass className="shrink-0" />
      <AlertDescription className="min-w-0 flex-1 text-foreground">
        You&apos;re exploring a demo. Nothing you do is saved.
      </AlertDescription>
      <Button size="sm" onClick={createAccount} className="shrink-0">Create an account</Button>
    </Alert>
  );
}
