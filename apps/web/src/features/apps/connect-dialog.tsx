import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { actions } from "@/data/store";
import type { Connector } from "@/data/types";
import { looksLikeEmail } from "@/lib/email";

/**
 * Connect an app. Gmail asks which account (the real app opens Google sign-in);
 * a custom MCP server asks for its URL.
 */
export function ConnectDialog({ connector, onClose }: { connector: Connector | null; onClose: () => void }) {
  const [value, setValue] = useState("");
  const isMcp = connector?.category === "mcp";
  const valid = isMcp ? /^https?:\/\/\S+$/.test(value.trim()) : looksLikeEmail(value);

  function connect() {
    if (!connector || !valid) return;
    const account = value.trim();
    actions.connectApp(connector.id, account);
    toast.success(`${connector.name} connected: ${account}`);
    setValue("");
    onClose();
  }

  return (
    <Dialog open={connector !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Connect {connector?.name}</DialogTitle>
          <DialogDescription>
            {isMcp ? "Its tools become tools your bots can use, each with a risk level you control." : "Your bots will read and draft email. Sending always follows each bot's security level."}
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            connect();
          }}
        >
          <Field>
            <FieldLabel htmlFor="connect-value">{isMcp ? "Server URL" : "Google account"}</FieldLabel>
            <Input id="connect-value" value={value} onChange={(e) => setValue(e.target.value)} placeholder={isMcp ? "https://mcp.example.com/sse" : "you@company.com"} autoFocus />
            <FieldDescription>{isMcp ? "A remote MCP server over HTTPS." : "In the real app this opens Google sign-in."}</FieldDescription>
          </Field>
          <DialogFooter className="mt-6">
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={!valid}>Connect</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
