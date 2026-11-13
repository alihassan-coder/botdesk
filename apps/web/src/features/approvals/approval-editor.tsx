import { useEffect, useId, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { FieldError } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { actions } from "@/data/store";
import type { Approval } from "@/data/types";
import { fieldErrorsFrom, formFields, initialValues, readValues, type ArgValues, type FieldErrors } from "@/lib/args-form";
import { ArgFieldInput } from "./arg-field-input";

interface ApprovalEditorProps {
  approval: Approval;
  /** Back to the card: `decided` after your decision, false on Cancel. */
  onClose: (decided: boolean) => void;
}

/**
 * "Edit" on an approval card: the action's arguments as a form built from the tool's schema,
 * filled in with what the bot asked for. Submitting approves your version. The first field
 * takes focus when it opens. If someone else decides first, the card takes over and says so;
 * any other failure keeps the form, and your changes, open.
 */
export function ApprovalEditor({ approval, onClose }: ApprovalEditorProps) {
  const args = useMemo(() => approval.args ?? {}, [approval.args]);
  const fields = useMemo(() => formFields(approval.argsSchema, args), [approval.argsSchema, args]);
  const [values, setValues] = useState<ArgValues>(() => initialValues(fields, args));
  const [errors, setErrors] = useState<FieldErrors>({});
  const [isSaving, setIsSaving] = useState(false);
  const idPrefix = useId();
  const formRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    formRef.current?.querySelector<HTMLElement>("input, textarea, select, button[role=checkbox]")?.focus();
  }, []);

  async function submit() {
    const read = readValues(fields, values, args);
    setErrors(read.errors);
    if (Object.keys(read.errors).length > 0) return;

    setIsSaving(true);
    const result = await actions.decideApproval(approval.id, "approve", read.args);
    setIsSaving(false);
    if (result.ok) return onClose(true);
    if (result.reason === "invalid") return setErrors(fieldErrorsFrom(result.error, fields));
    // Decided by someone else: the card now shows who, instead of this form.
    if (result.reason !== "conflict") toast.error(result.error);
  }

  return (
    <form
      ref={formRef}
      className="mt-3 flex flex-col gap-3"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      {fields.map((field) => (
        <ArgFieldInput
          key={field.name}
          field={field}
          idPrefix={idPrefix}
          value={values[field.name]}
          error={errors[field.name]}
          onChange={(value) => setValues((current) => ({ ...current, [field.name]: value }))}
        />
      ))}
      {errors[""] && <FieldError className="text-xs">{errors[""]}</FieldError>}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={isSaving}>
          {isSaving && <Spinner />} Approve edited version
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={() => onClose(false)} disabled={isSaving}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
