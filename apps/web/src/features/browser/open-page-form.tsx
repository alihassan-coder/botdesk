import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { actions } from "@/data/store";
import type { Bot } from "@/data/types";
import { toAddress } from "@/lib/browser";

/**
 * An address and Open: opens the page in the bot's browser, starting the browser if it's closed.
 * "example.com" opens https://example.com. The API's refusal (a private address, no browser
 * installed) shows under the field.
 */
export function OpenPageForm({ bot, label = "Address", onOpened }: { bot: Bot; label?: string; onOpened?: () => void }) {
  const [address, setAddress] = useState("");
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState("");
  const id = useId();

  async function open() {
    const url = toAddress(address);
    if (!url) return setError("Type an address, like example.com.");
    setOpening(true);
    setError("");
    const result = await actions.sendBrowserInput(bot.id, { kind: "open", url });
    setOpening(false);
    if (!result.ok) return setError(result.error);
    setAddress("");
    onOpened?.();
  }

  return (
    <form noValidate className="flex flex-col gap-1.5" onSubmit={(e) => { e.preventDefault(); if (!opening) void open(); }}>
      <label htmlFor={id} className="text-xs font-medium">{label}</label>
      <div className="flex gap-2">
        <Input id={id} inputMode="url" enterKeyHint="go" autoComplete="off" autoCapitalize="none" spellCheck={false}
          placeholder="example.com/login" value={address} onChange={(e) => { setAddress(e.target.value); setError(""); }}
          aria-invalid={error !== ""} aria-describedby={error ? `${id}-error` : undefined} />
        <Button type="submit" disabled={opening}>{opening ? "Opening…" : "Open"}</Button>
      </div>
      {error && <p id={`${id}-error`} role="alert" className="text-xs text-pretty text-destructive">{error}</p>}
    </form>
  );
}
