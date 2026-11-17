import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { actions, getStoreSnapshot } from "@/data/store";
import { HomeScreen } from "@/features/shell/home-screen";
import { MessageList } from "@/features/threads/message-list";
import { markOnboardingDone, onboardingDone } from "./done-flag";
import { renderUI } from "@/test/render";
import { apiMe, apiOrg, apiScout, signInOnApi, withFakeApi } from "@/test/fake-api";
import { WelcomeScreen } from "./welcome-screen";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, push: vi.fn() }), usePathname: () => "/" }));

const chief = { ...apiScout, id: "b2", name: "Chief", handle: "chief", role: "Chief of staff", description: "Plans the work, hands tasks to teammates and keeps you posted." };
const chiefDm = { id: "t2", kind: "dm", title: "Chief", botId: "b2", participants: [{ type: "user", id: "u1" }, { type: "bot", id: "b2" }], lastMessageAt: "2026-11-17T10:00:00Z", lastMessagePreview: "" };

const api = withFakeApi();
beforeEach(() => {
  replace.mockClear();
  Object.assign(api.routes, {
    "GET /api/v1/orgs/o1/bots": { status: 200, body: [] },
    "GET /api/v1/orgs/o1/threads": { status: 200, body: [] },
    "GET /api/v1/orgs/o1/providers": { status: 200, body: [] },
    "GET /api/v1/orgs/o1/models": { status: 200, body: { models: [], errors: [] } },
    "GET /api/v1/orgs/o1/connectors": { status: 200, body: [] },
    "GET /api/v1/orgs/o1/connections": { status: 200, body: [] },
  });
});

function signInAs(role: "owner" | "admin" | "member") {
  api.routes["POST /api/v1/auth/sign-in"] = { status: 200, body: { ...apiMe, organizations: [{ ...apiOrg, role }] } };
  api.routes["GET /api/v1/orgs/o1/members"] = { status: 200, body: [{ ...apiMe.user, role }] };
  return signInOnApi();
}

describe("Who goes to /welcome", () => {
  it("sends the owner of a new organization (no bots) from home to setup", async () => {
    await signInAs("owner");
    renderUI(<HomeScreen />);
    await vi.waitFor(() => expect(replace).toHaveBeenCalledWith("/welcome"));
  });

  const noSetup: [string, "owner" | "admin" | "member", () => void][] = [
    ["an invited member", "member", () => {}],
    ["an admin", "admin", () => {}],
    ["an owner whose team has bots", "owner", () => { api.routes["GET /api/v1/orgs/o1/bots"] = { status: 200, body: [apiScout] }; }],
    ["an owner who finished or skipped setup", "owner", () => markOnboardingDone("o1")],
  ];
  it.each(noSetup)("leaves %s in the app", async (_, role, arrange) => {
    arrange();
    await signInAs(role);
    renderUI(<HomeScreen />);
    await new Promise((r) => setTimeout(r, 20));
    expect(replace).not.toHaveBeenCalledWith("/welcome");
  });

  it("the demo never sends anyone to setup", () => {
    renderUI(<HomeScreen />);
    expect(replace).not.toHaveBeenCalledWith("/welcome");
  });

  it("sends a demo visitor who opens /welcome into the app", async () => {
    vi.unstubAllEnvs(); // no API: the demo, where Ali owns Acme
    await actions.signIn("ali@acme.dev", "botdesk123");
    renderUI(<WelcomeScreen />);
    await vi.waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
  });

  it("sends a member who opens /welcome into the app", async () => {
    await signInAs("member");
    renderUI(<WelcomeScreen />);
    await vi.waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    expect(screen.queryByText("Step 1 of 4")).not.toBeInTheDocument();
  });
});

describe("WelcomeScreen", () => {
  it("walks through the steps and Finish opens the first bot's DM, with its welcome message", async () => {
    api.routes["POST /api/v1/orgs/o1/bots"] = { status: 201, body: chief };
    api.routes["POST /api/v1/orgs/o1/threads/dm"] = { status: 200, body: chiefDm };
    await signInAs("owner");
    const { user } = renderUI(<WelcomeScreen />);

    expect(screen.getByText("Step 1 of 4")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Continue" })); // name unchanged: nothing to save
    expect(screen.getByRole("heading", { name: "Add an AI key" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Skip — bots will use a stand-in reply" }));
    await user.click(screen.getByRole("button", { name: "Hire Chief" }));
    await screen.findByText("Hired");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByText("Step 4 of 4")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Finish" }));

    expect(replace).toHaveBeenCalledWith("/chat/t2");
    expect(onboardingDone("o1")).toBe(true);
    expect(api.sent.some((r) => r.key === "PATCH /api/v1/orgs/o1")).toBe(false);

    // The new DM opens with Chief introducing itself.
    const dm = getStoreSnapshot().threads.find((t) => t.id === "t2")!;
    renderUI(<MessageList thread={dm} />);
    expect(screen.getByText("Hi! I'm Chief. Plans the work, hands tasks to teammates and keeps you posted. What should I work on first?")).toBeInTheDocument();
  });

  it("Skip setup goes home and never asks again for this org", async () => {
    await signInAs("owner");
    const { user } = renderUI(<WelcomeScreen />);
    await user.click(screen.getByRole("button", { name: "Skip setup" }));
    expect(replace).toHaveBeenCalledWith("/");
    expect(onboardingDone("o1")).toBe(true);
  });
});
