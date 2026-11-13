import type { ArgSchema, ArgsSchema } from "@/data/types";

/**
 * The Edit form on an approval card is built from the tool's JSON Schema: one field per
 * argument, pre-filled with what the bot asked for. Only simple schemas are supported
 * (strings, numbers, booleans and enums), which is what tools use today.
 */

export interface ArgField {
  name: string;
  label: string;
  kind: "text" | "textarea" | "number" | "boolean" | "enum";
  required: boolean;
  description?: string;
  /** What each option shows (and the form keeps as its value). */
  options?: string[];
  /** The schema's own values, in the same order: a numeric enum goes back as a number. */
  optionValues?: (string | number)[];
  integer?: boolean;
  email?: boolean;
  minLength?: number;
  maxLength?: number;
  minimum?: number;
  maximum?: number;
}

export type ArgValues = Record<string, string | boolean>;
export type FieldErrors = Record<string, string>;

/** Strings longer than this (or with line breaks) get a textarea. */
const LONG_TEXT = 80;
/** A string allowed to be this long is a body of text, not a one-liner. */
const LONG_LIMIT = 500;

/** "send_to" → "Send to", the same labels the API uses in an approval's preview. */
export const humanize = (key: string) => {
  const words = key.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1).toLowerCase();
};

/** One field per argument, in the schema's order. Without a schema, guessed from the values. */
export function formFields(schema: ArgsSchema | null | undefined, args: Record<string, unknown>): ArgField[] {
  const properties = schema?.properties;
  if (!properties) {
    return Object.entries(args).map(([name, value]) => fieldFor(name, guessSchema(value), false, value));
  }
  const required = new Set(schema.required ?? []);
  return Object.entries(properties).map(([name, property]) => fieldFor(name, plain(property), required.has(name), args[name]));
}

/** What the form starts with: the bot's arguments as form values. */
export function initialValues(fields: ArgField[], args: Record<string, unknown>): ArgValues {
  return Object.fromEntries(
    fields.map((field) => {
      const value = args[field.name];
      if (field.kind === "boolean") return [field.name, value === true];
      return [field.name, value === undefined || value === null ? "" : String(value)];
    }),
  );
}

/**
 * Checks the form like the API would and turns it back into arguments, or says what's wrong.
 * `original` is what the bot asked for: an optional field it left out stays out unless you
 * fill it in (an empty text or an unticked box isn't sent), so the tool's own default applies.
 */
export function readValues(
  fields: ArgField[],
  values: ArgValues,
  original: Record<string, unknown> = {},
): { args: Record<string, unknown>; errors: FieldErrors } {
  const args: Record<string, unknown> = {};
  const errors: FieldErrors = {};

  for (const field of fields) {
    const raw = values[field.name];
    const wasSent = field.name in original;
    if (field.kind === "boolean") {
      const checked = raw === true;
      if (wasSent || field.required || checked) args[field.name] = checked;
      continue;
    }
    const text = typeof raw === "string" ? raw : "";
    const problem = checkText(field, text);
    if (problem) {
      errors[field.name] = problem;
      continue;
    }
    const isText = field.kind === "text" || field.kind === "textarea";
    // Empty and optional: left out, except a text the bot sent, which you may clear on purpose.
    if (text === "" && !field.required && !(isText && wasSent)) continue;
    if (field.kind === "number") {
      if (text.trim() !== "") args[field.name] = Number(text);
    } else if (field.kind === "enum") {
      const at = field.options?.indexOf(text) ?? -1;
      args[field.name] = at === -1 ? text : (field.optionValues?.[at] ?? text);
    } else {
      args[field.name] = text;
    }
  }
  return { args, errors };
}

/**
 * The API's 400 answer, "Those changes don't fit this action: to: value is not a valid
 * email address; subject: String should have at least 1 character", as errors by field.
 * Problems not tied to a known field go under "" so the form can still show them.
 */
export function fieldErrorsFrom(message: string, fields: ArgField[]): FieldErrors {
  const detail = message.split(/action:\s*/)[1];
  if (!detail) return { "": message };
  const known = new Set(fields.map((f) => f.name));
  const errors: FieldErrors = {};
  for (const problem of detail.split(/;\s*/)) {
    const colon = problem.indexOf(": ");
    const where = colon === -1 ? "" : problem.slice(0, colon).split(".")[0];
    const what = colon === -1 ? problem : problem.slice(colon + 2);
    const key = known.has(where) ? where : "";
    errors[key] = errors[key] ? `${errors[key]} ${sentence(what)}` : sentence(what);
  }
  return errors;
}

/** The preview rows for a set of arguments, as the API makes them. */
export function previewFromArgs(args: Record<string, unknown>): { label: string; value: string }[] {
  return Object.entries(args).map(([key, value]) => ({ label: humanize(key), value: typeof value === "string" ? value : String(value) }));
}

function fieldFor(name: string, schema: ArgSchema, required: boolean, value: unknown): ArgField {
  const base = { name, label: schema.title ?? humanize(name), required, ...(schema.description ? { description: schema.description } : {}) };
  if (schema.enum) return { ...base, kind: "enum", options: schema.enum.map(String), optionValues: schema.enum };
  if (schema.type === "boolean") return { ...base, kind: "boolean" };
  if (schema.type === "number" || schema.type === "integer") {
    return { ...base, kind: "number", integer: schema.type === "integer", minimum: schema.minimum, maximum: schema.maximum };
  }
  const text = typeof value === "string" ? value : "";
  const isLong =
    schema.format === "textarea" || (schema.maxLength ?? 0) > LONG_LIMIT || text.includes("\n") || text.length > LONG_TEXT;
  return {
    ...base,
    kind: isLong ? "textarea" : "text",
    ...(schema.format === "email" ? { email: true } : {}),
    minLength: schema.minLength,
    maxLength: schema.maxLength,
  };
}

/** Optional arguments come as `anyOf: [{type: "string"}, {type: "null"}]`: use the real type. */
function plain(schema: ArgSchema): ArgSchema {
  const real = schema.anyOf?.find((option): option is ArgSchema => option.type !== "null");
  return real ? { ...real, ...schema, type: real.type } : schema;
}

function guessSchema(value: unknown): ArgSchema {
  if (typeof value === "boolean") return { type: "boolean" };
  if (typeof value === "number") return { type: "number" };
  return { type: "string" };
}

function checkText(field: ArgField, text: string): string | undefined {
  const empty = text.trim() === "";
  if (empty) return field.required && (field.minLength ?? 1) > 0 ? "Fill this in." : undefined;
  if (field.kind === "number") {
    const n = Number(text);
    if (!Number.isFinite(n)) return "Enter a number.";
    if (field.integer && !Number.isInteger(n)) return "Enter a whole number.";
    if (field.minimum !== undefined && n < field.minimum) return `Use ${field.minimum} or more.`;
    if (field.maximum !== undefined && n > field.maximum) return `Use ${field.maximum} or less.`;
    return undefined;
  }
  if (field.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text.trim())) return "Enter an email address, like sara@acme.dev.";
  if (field.minLength !== undefined && text.length < field.minLength) return `Use at least ${field.minLength} characters.`;
  if (field.maxLength !== undefined && text.length > field.maxLength) return `Use at most ${field.maxLength} characters.`;
  return undefined;
}

const sentence = (text: string) => {
  const trimmed = text.trim().replace(/\.$/, "");
  return `${trimmed.charAt(0).toUpperCase()}${trimmed.slice(1)}.`;
};
