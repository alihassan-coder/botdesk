import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { actions } from "@/data/store";
import type { ModelProvider } from "@/data/types";

/** Test on a connected key: checks it again with the provider. `mine` for your own key (My keys). */
export function TestKeyButton({ provider, mine = false }: { provider: ModelProvider; mine?: boolean }) {
  const [testing, setTesting] = useState(false);
  const test = async () => {
    setTesting(true);
    const result = await (mine ? actions.testMyKey(provider.id) : actions.testProviderKey(provider.id));
    setTesting(false);
    if (result.ok) toast.success(`${provider.name}: ${mine ? "your" : "the"} key works`);
    else toast.error(result.error);
  };
  return <Button size="sm" variant="outline" disabled={testing} onClick={test}>{testing ? "Testing…" : "Test"}</Button>;
}
