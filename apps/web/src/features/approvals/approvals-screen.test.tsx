import { act, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { actions } from "@/data/store";
import { renderUI } from "@/test/render";
import { ApprovalsScreen } from "./approvals-screen";

afterEach(() => vi.restoreAllMocks());

describe("ApprovalsScreen", () => {
  it("a failed load says so with Try again, instead of looking all caught up", async () => {
    const load = vi.spyOn(actions, "loadApprovals").mockResolvedValue({ ok: false, error: "Can't reach botdesk right now." });
    await act(() => actions.signIn("ali@acme.dev", "botdesk123"));
    const { user } = renderUI(<ApprovalsScreen />);

    expect(await screen.findByText("Couldn't load approvals")).toBeInTheDocument();
    expect(screen.getByText("Can't reach botdesk right now.")).toBeInTheDocument();
    expect(screen.queryByText("You're all caught up")).not.toBeInTheDocument();

    load.mockResolvedValue({ ok: true });
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(load).toHaveBeenCalledTimes(2);
    expect(await screen.findByRole("article", { name: "Decline vendor demo (Initech)" })).toBeInTheDocument();
  });
});
