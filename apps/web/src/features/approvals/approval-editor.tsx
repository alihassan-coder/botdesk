import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { Approval } from "@/data/types";

interface ApprovalEditorProps {
  preview: Approval["preview"];
  onApprove: (preview: Approval["preview"]) => void;
  onCancel: () => void;
}

/** "Edit" on an approval card: change any field of the action, then approve the edited version. */
export function ApprovalEditor({ preview, onApprove, onCancel }: ApprovalEditorProps) {
  const [fields, setFields] = useState(preview);

  const update = (label: string, value: string) =>
    setFields((current) => current.map((f) => (f.label === label ? { ...f, value } : f)));

  return (
    <form
      className="mt-3 flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        onApprove(fields);
      }}
    >
      {fields.map((field, index) => {
        const id = `approval-field-${field.label}`;
        // Decide from the ORIGINAL value: switching box type while typing would lose focus and your text.
        const original = preview[index].value;
        const isLong = original.includes("\n") || original.length > 60;
        return (
          <div key={field.label} className="flex flex-col gap-1.5">
            <Label htmlFor={id} className="text-xs text-muted-foreground">
              {field.label}
            </Label>
            {isLong ? (
              <Textarea id={id} value={field.value} onChange={(e) => update(field.label, e.target.value)} rows={5} />
            ) : (
              <Input id={id} value={field.value} onChange={(e) => update(field.label, e.target.value)} />
            )}
          </div>
        );
      })}
      <div className="flex gap-2">
        <Button type="submit" size="sm">
          Approve edited version
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
