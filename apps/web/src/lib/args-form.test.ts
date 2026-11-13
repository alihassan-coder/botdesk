import { describe, expect, it } from "vitest";
import type { ArgsSchema } from "@/data/types";
import { fieldErrorsFrom, formFields, initialValues, previewFromArgs, readValues } from "./args-form";

/* The schema pydantic gives the demo plugin's EmailArgs, plus a few other kinds of field. */
const emailSchema: ArgsSchema = {
  type: "object",
  properties: {
    to: { type: "string", title: "To", format: "email" },
    subject: { type: "string", title: "Subject", minLength: 1, maxLength: 200 },
    body: { type: "string", title: "Body", maxLength: 10_000, default: "" },
  },
  required: ["to", "subject"],
};
const args = { to: "sara@acme.dev", subject: "Launch", body: "See you Thursday" };

describe("formFields", () => {
  it("makes one field per argument, in the schema's order, with the right input", () => {
    expect(formFields(emailSchema, args)).toEqual([
      { name: "to", label: "To", kind: "text", required: true, email: true, minLength: undefined, maxLength: undefined },
      { name: "subject", label: "Subject", kind: "text", required: true, minLength: 1, maxLength: 200 },
      { name: "body", label: "Body", kind: "textarea", required: false, minLength: undefined, maxLength: 10_000 },
    ]);
  });

  it("reads numbers, booleans, enums and optional (anyOf null) arguments", () => {
    const schema: ArgsSchema = {
      properties: {
        amount: { type: "integer", minimum: 1 },
        urgent: { type: "boolean" },
        tone: { type: "string", enum: ["friendly", "formal"] },
        note_to_self: { anyOf: [{ type: "string" }, { type: "null" }], title: "Note to self" },
      },
    };
    const fields = formFields(schema, {});
    expect(fields.map((f) => [f.name, f.label, f.kind])).toEqual([
      ["amount", "Amount", "number"],
      ["urgent", "Urgent", "boolean"],
      ["tone", "Tone", "enum"],
      ["note_to_self", "Note to self", "text"],
    ]);
    expect(fields[0]).toMatchObject({ integer: true, minimum: 1 });
    expect(fields[2].options).toEqual(["friendly", "formal"]);
    expect(fields[2].optionValues).toEqual(["friendly", "formal"]);
  });

  it("long or multi-line text gets a textarea even without a long limit", () => {
    expect(formFields({ properties: { note: { type: "string" } } }, { note: "line one\nline two" })[0].kind).toBe("textarea");
    expect(formFields({ properties: { note: { type: "string" } } }, { note: "x".repeat(81) })[0].kind).toBe("textarea");
  });

  it("without a schema, guesses from the values", () => {
    expect(formFields(null, { site: "staging", retries: 2, dryRun: true }).map((f) => f.kind)).toEqual(["text", "number", "boolean"]);
  });
});

describe("initialValues and readValues", () => {
  const fields = formFields(emailSchema, args);

  it("round-trips the bot's arguments", () => {
    const values = initialValues(fields, args);
    expect(values).toEqual(args);
    expect(readValues(fields, values)).toEqual({ args, errors: {} });
  });

  it("says what's wrong with each field, in plain words", () => {
    const { errors } = readValues(fields, { to: "not-an-email", subject: "", body: "x" });
    expect(errors).toEqual({ to: "Enter an email address, like sara@acme.dev.", subject: "Fill this in." });
  });

  it("checks lengths and numbers", () => {
    const schema: ArgsSchema = { properties: { code: { type: "string", maxLength: 3 }, amount: { type: "integer", maximum: 10 } }, required: ["amount"] };
    const numeric = formFields(schema, {});
    expect(readValues(numeric, { code: "abcd", amount: "2.5" }).errors).toEqual({ code: "Use at most 3 characters.", amount: "Enter a whole number." });
    expect(readValues(numeric, { code: "", amount: "11" }).errors).toEqual({ amount: "Use 10 or less." });
    expect(readValues(numeric, { code: "ab", amount: "7" })).toEqual({ args: { code: "ab", amount: 7 }, errors: {} });
  });

  it("booleans come back as booleans, and an unticked one the bot left out stays out", () => {
    const flags = formFields({ properties: { urgent: { type: "boolean" } } }, {});
    expect(initialValues(flags, {})).toEqual({ urgent: false });
    expect(readValues(flags, { urgent: true }).args).toEqual({ urgent: true });
    expect(readValues(flags, { urgent: false }).args).toEqual({});
    expect(readValues(flags, { urgent: false }, { urgent: false }).args).toEqual({ urgent: false });
  });

  it("an optional text the bot left out isn't sent as \"\"; one it sent can be cleared", () => {
    const schema: ArgsSchema = { properties: { cc: { type: "string" }, note: { type: "string" } } };
    const optional = formFields(schema, { note: "Hi" });
    expect(readValues(optional, { cc: "", note: "" }, { note: "Hi" }).args).toEqual({ note: "" });
    expect(readValues(optional, { cc: "omar@acme.dev", note: "Hi" }, { note: "Hi" }).args).toEqual({ cc: "omar@acme.dev", note: "Hi" });
  });

  it("a numeric enum goes back as a number; numbers must be finite", () => {
    const schema: ArgsSchema = { properties: { priority: { type: "integer", enum: [1, 2, 3] }, amount: { type: "number" } }, required: ["priority"] };
    const fields = formFields(schema, { priority: 2 });
    expect(fields[0].kind).toBe("enum");
    expect(readValues(fields, { priority: "3", amount: "" }, { priority: 2 }).args).toEqual({ priority: 3 });
    expect(readValues(fields, { priority: "3", amount: "Infinity" }).errors).toEqual({ amount: "Enter a number." });
  });
});

describe("fieldErrorsFrom (the API's 400 answer)", () => {
  const fields = formFields(emailSchema, args);

  it("splits the problems by argument", () => {
    const message = "Those changes don't fit this action: to: value is not a valid email address: An email address must have an @-sign.; subject: String should have at least 1 character";
    expect(fieldErrorsFrom(message, fields)).toEqual({
      to: "Value is not a valid email address: An email address must have an @-sign.",
      subject: "String should have at least 1 character.",
    });
  });

  it("problems not tied to a field, or a message it can't read, go under the form", () => {
    expect(fieldErrorsFrom("Those changes don't fit this action: args: Extra inputs are not permitted", fields)).toEqual({ "": "Extra inputs are not permitted." });
    expect(fieldErrorsFrom("Something else went wrong.", fields)).toEqual({ "": "Something else went wrong." });
  });
});

it("previewFromArgs labels rows the way the API does", () => {
  expect(previewFromArgs({ send_to: "sara@acme.dev", count: 2 })).toEqual([
    { label: "Send to", value: "sara@acme.dev" },
    { label: "Count", value: "2" },
  ]);
});
