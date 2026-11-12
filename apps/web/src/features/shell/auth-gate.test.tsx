import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { actions } from "@/data/store";
import { AuthGate } from "./auth-gate";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

beforeEach(() => replace.mockClear());

describe("AuthGate", () => {
  it("keeps the page rendered but hidden until you're signed in, then sends you to sign in", () => {
    render(<AuthGate><p>The page</p></AuthGate>);

    // Rendered (Next.js prerenders every route segment under the gate), but not shown or usable.
    expect(screen.getByText("The page", { selector: "p" })).not.toBeVisible();
    expect(screen.getByLabelText("Loading botdesk")).toBeInTheDocument();
    expect(replace).toHaveBeenCalledWith("/sign-in");
  });

  it("shows the page once you're signed in", async () => {
    await actions.signIn("ali@acme.dev", "botdesk123");
    render(<AuthGate><p>The page</p></AuthGate>);

    expect(screen.getByText("The page")).toBeVisible();
    expect(screen.queryByLabelText("Loading botdesk")).not.toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});
