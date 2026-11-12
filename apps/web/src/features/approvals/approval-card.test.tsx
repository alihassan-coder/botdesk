import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { ApprovalCard } from "./approval-card";

describe("ApprovalCard", () => {
  it("shows exactly what the bot wants to do, and the risk", () => {
    renderUI(<ApprovalCard approvalId="a_1" />);

    expect(screen.getByText("Send reply to Vicky (Globex)")).toBeInTheDocument();
    expect(screen.getByText("Sends outside your org")).toBeInTheDocument();
    expect(screen.getByText("vicky@globex.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
  });

  it("Approve marks it approved by you and hides the buttons", async () => {
    const { user } = renderUI(<ApprovalCard approvalId="a_1" />);
    await user.click(screen.getByRole("button", { name: "Approve" }));

    expect(screen.getByText(/Approved by you/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("Deny marks it denied", async () => {
    const { user } = renderUI(<ApprovalCard approvalId="a_2" />);
    await user.click(screen.getByRole("button", { name: "Deny" }));
    expect(screen.getByText(/Denied by you/)).toBeInTheDocument();
  });

  it("Edit lets you change the action, then approves the edited version", async () => {
    const { user } = renderUI(<ApprovalCard approvalId="a_2" />);
    await user.click(screen.getByRole("button", { name: "Edit" }));

    const body = screen.getByLabelText("Body");
    await user.clear(body);
    await user.type(body, "Not this quarter, thanks.");
    await user.click(screen.getByRole("button", { name: "Approve edited version" }));

    const approval = getStoreSnapshot().approvals.find((a) => a.id === "a_2");
    expect(approval?.status).toBe("approved");
    expect(approval?.preview.find((f) => f.label === "Body")?.value).toBe("Not this quarter, thanks.");
    expect(screen.getByText(/Approved by you/)).toBeInTheDocument();
  });

  it("Cancel leaves the action untouched", async () => {
    const { user } = renderUI(<ApprovalCard approvalId="a_2" />);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(getStoreSnapshot().approvals.find((a) => a.id === "a_2")?.status).toBe("pending");
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
  });

  it("shows a past decision instead of buttons", () => {
    renderUI(<ApprovalCard approvalId="a_4" />);
    expect(screen.getByText(/Approved by you/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
