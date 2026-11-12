import { Compass } from "lucide-react";
import { Button } from "@/components/ui/button";
import { actions } from "@/data/store";

/**
 * Look around without an account: opens the demo team as a guest. The auth page's
 * signed-in redirect then takes you into the app.
 */
export function ExploreDemoButton() {
  return (
    <Button variant="ghost" size="lg" onClick={() => actions.enterGuestMode()}>
      <Compass /> Explore the demo, no account needed
    </Button>
  );
}
