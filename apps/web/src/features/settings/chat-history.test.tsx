import { screen, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { apiMe, apiOrg, signInOnApi, withFakeApi } from "@/test/fake-api";
import { ChatHistory } from "./chat-history";

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock("sonner", () => ({ toast: { success: (m: string) => toastSuccess(m), error: (m: string) => toastError(m) } }));

beforeEach(() => {
  toastSuccess.mockClear();
  toastError.mockClear();
});

const summaries = () => screen.getByRole("switch", { name: "Bots read a summary of older messages" });
const retention = () => screen.getByRole("combobox", { name: "Delete messages older than" });

async function pick(user: UserEvent, label: string) {
  await user.click(retention());
  await user.click(screen.getByRole("option", { name: label }));
}

describe("Settings → Organization's chat history, in the demo", () => {
  it("summaries are on to start, and turning them off asks nothing", async () => {
    const { user } = renderUI(<ChatHistory />);
    expect(summaries()).toBeChecked();
    expect(screen.getByText(/reads a chat's last 30 messages word for word/)).toHaveTextContent("about one model call per 20 messages");

    await user.click(summaries());
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(summaries()).not.toBeChecked();
    expect(getStoreSnapshot().org.historySummaries).toBe(false);
  });

  it("a limit asks first, saying plainly what it deletes; keeping messages saves nothing", async () => {
    const { user } = renderUI(<ChatHistory />);
    expect(retention()).toHaveTextContent("Never");
    await pick(user, "90 days");

    const dialog = within(screen.getByRole("alertdialog", { name: "Delete messages older than 90 days?" }));
    expect(dialog.getByText(/Every night, messages older than 90 days are deleted for everyone in Acme Labs/)).toHaveTextContent(
      "This can't be undone. Runs, approvals, usage and files stay, and so does each chat's summary.",
    );
    await user.click(dialog.getByRole("button", { name: "Keep messages" }));
    expect(getStoreSnapshot().org.historyRetentionDays).toBeNull();
    expect(retention()).toHaveTextContent("Never");

    await pick(user, "90 days");
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Delete older messages" }));
    expect(getStoreSnapshot().org.historyRetentionDays).toBe(90);
    expect(retention()).toHaveTextContent("90 days");
    expect(toastSuccess).toHaveBeenCalledWith("Messages older than 90 days will be deleted every night");
  });
});

describe("Settings → Organization's chat history, on the API", () => {
  const api = withFakeApi();
  const PATCH = "PATCH /api/v1/orgs/o1";
  const patches = () => api.sent.filter((s) => s.key === PATCH).map((s) => s.body);

  it("turns summaries off with the PATCH, and shows the API's refusal by putting the switch back", async () => {
    await signInOnApi();
    api.routes[PATCH] = { status: 200, body: { ...apiOrg, historySummaries: false, historyRetentionDays: null } };
    const { user } = renderUI(<ChatHistory />);
    await user.click(summaries());
    await vi.waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Bots now read only the last 30 messages"));
    expect(patches()).toEqual([{ historySummaries: false }]);
    expect(summaries()).not.toBeChecked();

    api.routes[PATCH] = { status: 403, body: { detail: "Only owners and admins can do that." } };
    await user.click(summaries());
    await vi.waitFor(() => expect(toastError).toHaveBeenCalledWith("Only owners and admins can do that."));
    expect(summaries()).not.toBeChecked();
  });

  it("a shorter limit asks first and then sends it; a longer one and Never don't ask, and Never sends null", async () => {
    api.routes["POST /api/v1/auth/sign-in"] = { status: 200, body: { ...apiMe, organizations: [{ ...apiOrg, historyRetentionDays: 90 }] } };
    await signInOnApi();
    const { user } = renderUI(<ChatHistory />);
    expect(retention()).toHaveTextContent("90 days");

    api.routes[PATCH] = { status: 200, body: { ...apiOrg, historyRetentionDays: 30 } };
    await pick(user, "30 days");
    expect(patches()).toEqual([]);
    await user.click(within(screen.getByRole("alertdialog", { name: "Delete messages older than 30 days?" })).getByRole("button", { name: "Delete older messages" }));
    await vi.waitFor(() => expect(retention()).toHaveTextContent("30 days"));

    api.routes[PATCH] = { status: 200, body: { ...apiOrg, historyRetentionDays: 365 } };
    await pick(user, "1 year");
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    await vi.waitFor(() => expect(retention()).toHaveTextContent("1 year"));

    api.routes[PATCH] = { status: 200, body: { ...apiOrg, historyRetentionDays: null } };
    await pick(user, "Never");
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    await vi.waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Messages are kept forever"));
    expect(patches()).toEqual([{ historyRetentionDays: 30 }, { historyRetentionDays: 365 }, { historyRetentionDays: null }]);
    expect(getStoreSnapshot().orgs[0]).toMatchObject({ historyRetentionDays: null });
  });

  it("members see both settings but can't change them", async () => {
    api.routes["POST /api/v1/auth/sign-in"] = {
      status: 200, body: { ...apiMe, organizations: [{ ...apiOrg, role: "member", historySummaries: false, historyRetentionDays: 180 }] },
    };
    api.routes["GET /api/v1/orgs/o1/members"] = { status: 200, body: [{ ...apiMe.user, role: "member" }] };
    await signInOnApi();
    renderUI(<ChatHistory />);
    expect(summaries()).not.toBeChecked();
    expect(summaries()).toBeDisabled();
    expect(retention()).toHaveTextContent("180 days");
    expect(retention()).toBeDisabled();
    expect(screen.getByText("Only owners and admins can change chat history.")).toBeInTheDocument();
  });
});
