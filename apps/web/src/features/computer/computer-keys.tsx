import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from "@/components/ui/input-group";
import type { ComputerKey } from "@/data/types";
import { KEY_BUTTONS } from "@/lib/computer";

interface ComputerKeysProps {
  botName: string;
  onKey: (key: ComputerKey) => void;
  onType: (text: string) => void;
}

/**
 * Under a taken-over computer screen: buttons for the keys a touch screen can't press (and shortcuts
 * this browser would keep), and a field for typing text on the computer, sent when you press Type.
 */
export function ComputerKeys({ botName, onKey, onType }: ComputerKeysProps) {
  const [text, setText] = useState("");
  const fieldId = useId();

  return (
    <div className="flex flex-col gap-3">
      <div role="toolbar" aria-label={`Keys for ${botName}'s computer`} className="flex flex-wrap gap-1.5">
        {KEY_BUTTONS.map(({ key, label, name }) => (
          <Button key={key} type="button" size="sm" variant="outline" aria-label={name ? `Press ${name}` : `Press ${label}`}
            className="font-mono" onClick={() => onKey(key)}>
            {label}
          </Button>
        ))}
      </div>
      <form className="flex flex-col gap-1.5" onSubmit={(e) => {
        e.preventDefault();
        if (!text) return;
        onType(text);
        setText("");
      }}>
        <label htmlFor={fieldId} className="text-xs text-muted-foreground">Type on the computer</label>
        <InputGroup>
          <InputGroupInput id={fieldId} value={text} onChange={(e) => setText(e.target.value)} autoComplete="off" autoCapitalize="none"
            spellCheck={false} placeholder="Text to type where its cursor is" />
          <InputGroupAddon align="inline-end">
            <InputGroupButton type="submit" size="xs" disabled={!text}>Type</InputGroupButton>
          </InputGroupAddon>
        </InputGroup>
      </form>
    </div>
  );
}
