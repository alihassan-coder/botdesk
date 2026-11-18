import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { apiMe, apiOrg, signInOnApi, withFakeApi } from "@/test/fake-api";
import { SecuritySettings } from "./security-settings";

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock("sonner", () => ({ toast: { success: (m: string) => toastSuccess(m), error: (m: string) => toastError(m) } }));

beforeEach(() => {
  toastSuccess.mockClear();
  toastError.mockClear();
});

const defaultPicker = () => within(screen.getByRole("radiogroup", { name: "Default security level" }));
const ceilingPicker = () => within(screen.getByRole("radiogroup", { name: "Highest security level" }));

describe("Settings → Security's default for new bots, in the demo", () => {
  it("saves the choice for the demo's next bots", async () => {
    const { user } = renderUI(<SecuritySettings />);
    await user.click(defaultPicker().getByRole("radio", { name: /^Read only/ }));
    expect(getStoreSnapshot().org.defaultSecurityLevel).toBe("read-only");
    expect(toastSuccess).toHaveBeenCalledWith("Default security level saved");
  });
});

describe("Settings → Security's default for new bots, on the API", () => {
  const api = withFakeApi();

  it("shows the org's saved default", async () => {
    api.routes["POST /api/v1/auth/sign-in"] = { status: 200, body: { ...apiMe, organizations: [{ ...apiOrg, defaultSecurityLevel: "read-only" }] } };
    await signInOnApi();
    renderUI(<SecuritySettings />);
    expect(defaultPicker().getByRole("radio", { name: /^Read only/ })).toBeChecked();
  });

  it("saves on the API and says so only once it's saved", async () => {
    await signInOnApi();
    api.routes["PATCH /api/v1/orgs/o1"] = { status: 200, body: { ...apiOrg, defaultSecurityLevel: "autonomous" } };
    const { user } = renderUI(<SecuritySettings />);
    await user.click(defaultPicker().getByRole("radio", { name: /^Autonomous/ }));

    await vi.waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Default security level saved"));
    expect(api.sent.find((r) => r.key === "PATCH /api/v1/orgs/o1")?.body).toEqual({ defaultSecurityLevel: "autonomous" });
    expect(defaultPicker().getByRole("radio", { name: /^Autonomous/ })).toBeChecked();
  });

  it("shows the API's refusal and keeps the saved default", async () => {
    await signInOnApi();
    api.routes["PATCH /api/v1/orgs/o1"] = { status: 403, body: { detail: "Only owners and admins can do that." } };
    const { user } = renderUI(<SecuritySettings />);
    await user.click(defaultPicker().getByRole("radio", { name: /^Autonomous/ }));

    await vi.waitFor(() => expect(toastError).toHaveBeenCalledWith("Only owners and admins can do that."));
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(defaultPicker().getByRole("radio", { name: /^Ask before acting/ })).toBeChecked();
  });

  it("members see the default but can't change it", async () => {
    api.routes["POST /api/v1/auth/sign-in"] = { status: 200, body: { ...apiMe, organizations: [{ ...apiOrg, role: "member" }] } };
    api.routes["GET /api/v1/orgs/o1/members"] = { status: 200, body: [{ ...apiMe.user, role: "member" }] };
    await signInOnApi();
    renderUI(<SecuritySettings />);
    expect(defaultPicker().getByRole("radio", { name: /^Autonomous/ })).toBeDisabled();
    expect(screen.getByText("Only owners and admins can change the default.")).toBeInTheDocument();
  });
});

describe("Settings → Security's ceiling for every bot, in the demo", () => {
  it("starts with no ceiling, then caps the bots above it and the default, saying why", async () => {
    const { user } = renderUI(<SecuritySettings />);
    expect(ceilingPicker().getByRole("radio", { name: /^Autonomous/ })).toBeChecked();

    await user.click(ceilingPicker().getByRole("radio", { name: /^Read only/ }));

    expect(getStoreSnapshot().org.maxSecurityLevel).toBe("read-only");
    expect(toastSuccess).toHaveBeenCalledWith("Highest security level saved");
    expect(screen.getAllByText("Capped at Read only by the organization").length).toBeGreaterThan(0);
    // The default comes down with it, and nothing above the ceiling can be picked for new bots.
    expect(getStoreSnapshot().org.defaultSecurityLevel).toBe("read-only");
    expect(defaultPicker().getByRole("radio", { name: /^Read only/ })).toBeChecked();
    expect(defaultPicker().getByRole("radio", { name: /^Ask before acting/ })).toBeDisabled();
  });

  it("a bot's own level can't be raised above the ceiling from the list", async () => {
    const { user } = renderUI(<SecuritySettings />);
    await user.click(ceilingPicker().getByRole("radio", { name: /^Ask before acting/ }));
    const bot = getStoreSnapshot().bots.find((b) => b.securityLevel !== "autonomous")!;

    await user.click(screen.getByRole("combobox", { name: `Security level for ${bot.name}` }));

    expect(screen.getByRole("option", { name: "Autonomous within limits" })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("option", { name: "Read only" })).not.toHaveAttribute("aria-disabled", "true");
  });
});

describe("Settings → Security's ceiling, on the API", () => {
  const api = withFakeApi();

  it("saves the ceiling, and the default the API lowered with it", async () => {
    await signInOnApi();
    api.routes["PATCH /api/v1/orgs/o1"] = { status: 200, body: { ...apiOrg, maxSecurityLevel: "read-only", defaultSecurityLevel: "read-only" } };
    const { user } = renderUI(<SecuritySettings />);
    await user.click(ceilingPicker().getByRole("radio", { name: /^Read only/ }));

    await vi.waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Highest security level saved"));
    expect(api.sent.find((r) => r.key === "PATCH /api/v1/orgs/o1")?.body).toEqual({ maxSecurityLevel: "read-only" });
    expect(getStoreSnapshot().org).toMatchObject({ maxSecurityLevel: "read-only", defaultSecurityLevel: "read-only" });
    expect(getStoreSnapshot().orgs[0]).toMatchObject({ maxSecurityLevel: "read-only", defaultSecurityLevel: "read-only" });
  });

  it("shows the API's refusal and keeps the saved ceiling", async () => {
    await signInOnApi();
    api.routes["PATCH /api/v1/orgs/o1"] = { status: 403, body: { detail: "Only owners and admins can do that." } };
    const { user } = renderUI(<SecuritySettings />);
    await user.click(ceilingPicker().getByRole("radio", { name: /^Read only/ }));

    await vi.waitFor(() => expect(toastError).toHaveBeenCalledWith("Only owners and admins can do that."));
    expect(ceilingPicker().getByRole("radio", { name: /^Autonomous/ })).toBeChecked();
  });

  it("members see the ceiling but can't change it", async () => {
    api.routes["POST /api/v1/auth/sign-in"] = {
      status: 200,
      body: { ...apiMe, organizations: [{ ...apiOrg, role: "member", maxSecurityLevel: "read-only", defaultSecurityLevel: "read-only" }] },
    };
    api.routes["GET /api/v1/orgs/o1/members"] = { status: 200, body: [{ ...apiMe.user, role: "member" }] };
    await signInOnApi();
    renderUI(<SecuritySettings />);
    expect(ceilingPicker().getByRole("radio", { name: /^Read only/ })).toBeChecked();
    expect(ceilingPicker().getByRole("radio", { name: /^Autonomous/ })).toBeDisabled();
    expect(screen.getByText("Only owners and admins can change the highest level.")).toBeInTheDocument();
  });
});
