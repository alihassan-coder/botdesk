import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { templates } from "./fixtures";

/*
 * One catalogue: the API serves `apps/api/src/templates/catalogue.json`, and the demo shows the
 * same templates (plus made-up hire counts). The web can't import the API's file at run time (its
 * Docker image has only apps/web), so this test keeps the copy word for word.
 */
// Vitest runs from apps/web.
const catalogue: unknown[] = JSON.parse(readFileSync(join(process.cwd(), "../api/src/templates/catalogue.json"), "utf-8"));

describe("the demo's marketplace", () => {
  it("is the API's catalogue", () => {
    const withoutHires = templates.map((template) => {
      const copy: Partial<typeof template> = { ...template };
      delete copy.installs;
      return copy;
    });
    expect(withoutHires).toEqual(catalogue);
  });

  it("has Chief, with its chief-of-staff instructions", () => {
    const chief = templates.find((t) => t.id === "chief");
    expect(chief?.instructions).toMatch(/chief of staff.*team\.handoff/);
  });
});
