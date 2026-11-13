import { useState } from "react";
import { act, fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { actions, getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { ApprovalCard } from "./approval-card";

/** The card, plus a button that makes it render again (like a clock tick). */
function WithRerender() {
  const [renders, setRenders] = useState(0);
  return (
    <>
      <button type="button" onClick={() => setRenders(renders + 1)}>Render again {renders}</button>
      <ApprovalCard approvalId="a_2" />
    </>
  );
}

const approval = (id: string) => getStoreSnapshot().approvals.find((a) => a.id === id);

describe("ApprovalCard", () => {
  it("shows exactly what the bot wants to do, the risk and why it asked", () => {
    renderUI(<ApprovalCard approvalId="a_2" />);

    expect(screen.getByText("Decline vendor demo (Initech)")).toBeInTheDocument();
    expect(screen.getByText("Sends outside your org")).toBeInTheDocument();
    expect(screen.getByText("sales@initech.com")).toBeInTheDocument();
    expect(screen.getByText("Asked because the bot is set to “Ask before acting”.")).toBeInTheDocument();
    expect(screen.queryByText("This bot read outside content first")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
  });

  it("warns when the run read outside content", () => {
    renderUI(<ApprovalCard approvalId="a_1" />);
    expect(screen.getByText("This bot read outside content first")).toBeInTheDocument();
  });

  it("Approve marks it approved by you and hides the buttons", async () => {
    const { user } = renderUI(<ApprovalCard approvalId="a_1" />);
    await user.click(screen.getByRole("button", { name: "Approve" }));

    expect(await screen.findByText(/Approved by you/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("Deny marks it denied", async () => {
    const { user } = renderUI(<ApprovalCard approvalId="a_2" />);
    await user.click(screen.getByRole("button", { name: "Deny" }));
    expect(await screen.findByText(/Denied by you/)).toBeInTheDocument();
  });

  it("Edit opens a form filled in from the action, and approves your version", async () => {
    const { user } = renderUI(<ApprovalCard approvalId="a_2" />);
    await user.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.getByLabelText("To")).toHaveValue("sales@initech.com");
    const body = screen.getByLabelText(/Body/);
    await user.clear(body);
    await user.type(body, "Not this quarter, thanks.");
    await user.click(screen.getByRole("button", { name: "Approve edited version" }));

    expect(approval("a_2")).toMatchObject({ status: "edited", finalArgs: { body: "Not this quarter, thanks." } });
    expect(approval("a_2")?.preview.find((f) => f.label === "Body")?.value).toBe("Not this quarter, thanks.");
    expect(await screen.findByText(/Edited and approved by you/)).toBeInTheDocument();
  });

  it("Cancel leaves the action untouched", async () => {
    const { user } = renderUI(<ApprovalCard approvalId="a_2" />);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(approval("a_2")?.status).toBe("pending");
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
  });

  it("shows a past decision instead of buttons", () => {
    renderUI(<ApprovalCard approvalId="a_4" />);
    expect(screen.getByText(/Approved by you/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("Edit focuses the first field, and Cancel puts focus back on Edit", async () => {
    const { user } = renderUI(<ApprovalCard approvalId="a_2" />);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByLabelText("To")).toHaveFocus();

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Edit" })).toHaveFocus();
  });

  it("after you decide, focus moves to the decision line and it's announced", async () => {
    const { user } = renderUI(<ApprovalCard approvalId="a_1" />);
    const live = document.querySelector("[aria-live=polite]");
    expect(live).toBeEmptyDOMElement(); // mounted before anything is decided

    await user.click(screen.getByRole("button", { name: "Approve" }));

    expect(await screen.findByText(/^Approved by you/, { selector: "p[tabindex]" })).toHaveFocus();
    expect(live).toHaveTextContent("Approved by you");
  });

  it("someone else deciding while you edit says who, instead of silently dropping the form", async () => {
    const { user } = renderUI(<ApprovalCard approvalId="a_2" />);
    await user.click(screen.getByRole("button", { name: "Edit" }));

    await act(async () => {
      await actions.signIn("sara@acme.dev", "botdesk123");
      await actions.decideApproval("a_2", "deny");
      await actions.signIn("ali@acme.dev", "botdesk123");
    });

    expect(screen.queryByRole("button", { name: "Approve edited version" })).not.toBeInTheDocument();
    expect(screen.getByText("Sara Khan already denied this, so your changes weren't used.")).toBeInTheDocument();
    expect(screen.getByText(/^Denied by Sara Khan/, { selector: "p[tabindex]" })).toHaveFocus();
  });

  it("after someone else decides, focus moves to the decision line once, not again on later renders", async () => {
    const { user } = renderUI(<WithRerender />);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await act(async () => {
      await actions.signIn("sara@acme.dev", "botdesk123");
      await actions.decideApproval("a_2", "deny");
      await actions.signIn("ali@acme.dev", "botdesk123");
    });
    const decisionLine = screen.getByText(/^Denied by Sara Khan/, { selector: "p[tabindex]" });
    expect(decisionLine).toHaveFocus();

    // You click somewhere else on the page; the card renders again (a clock tick, a store update).
    act(() => decisionLine.blur());
    fireEvent.click(screen.getByRole("button", { name: /Render again/ })); // a click that doesn't move focus
    expect(screen.getByRole("button", { name: "Render again 1" })).toBeInTheDocument();

    expect(decisionLine).not.toHaveFocus();
    expect(screen.queryByRole("button", { name: "Approve edited version" })).not.toBeInTheDocument();
    expect(screen.getByText("Sara Khan already denied this, so your changes weren't used.")).toBeInTheDocument();
  });
});
