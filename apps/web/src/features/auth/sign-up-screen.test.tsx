import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderUI } from "@/test/render";
import { apiMe, withFakeApi } from "@/test/fake-api";
import { SignUpScreen } from "./sign-up-screen";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, push: vi.fn() }) }));

const BY_INVITATION = "Sign-up is by invitation. Ask your admin for an invite link.";

describe("SignUpScreen in demo mode", () => {
  it("shows the form, as before (no API, nothing to ask)", async () => {
    renderUI(<SignUpScreen inviteToken={null} />);
    expect(await screen.findByRole("button", { name: "Create account" })).toBeInTheDocument();
  });
});

describe("SignUpScreen on the API", () => {
  const api = withFakeApi();
  const mode = (signUpMode: string) => (api.routes["GET /api/v1/auth/options"] = { status: 200, body: { signUpMode } });

  it("open: the form", async () => {
    mode("open");
    renderUI(<SignUpScreen inviteToken={null} />);
    expect(await screen.findByRole("button", { name: "Create account" })).toBeInTheDocument();
  });

  it("invite-only without an invite: says how to get in, no form", async () => {
    mode("invite-only");
    renderUI(<SignUpScreen inviteToken={null} />);
    expect(await screen.findByText(BY_INVITATION)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create account" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/sign-in");
  });

  it("invite-only from an invite link: the form, and the invite goes with the sign-up", async () => {
    mode("invite-only");
    api.routes["POST /api/v1/auth/sign-up"] = { status: 201, body: apiMe };
    api.routes["GET /api/v1/orgs/o1/members"] = { status: 200, body: [] };
    const { user } = renderUI(<SignUpScreen inviteToken="tok123" />);

    await user.type(await screen.findByLabelText("Your name"), "Zara");
    await user.type(screen.getByLabelText("Work email"), "zara@example.com");
    await user.type(screen.getByLabelText("Password"), "long-enough");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    await vi.waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    const sent = api.sent.find((r) => r.key === "POST /api/v1/auth/sign-up");
    expect(sent?.body).toEqual({ name: "Zara", email: "zara@example.com", password: "long-enough", inviteToken: "tok123" });
  });

  it("closed: no form, a note instead", async () => {
    mode("closed");
    renderUI(<SignUpScreen inviteToken="tok123" />);
    expect(await screen.findByText(/New accounts are turned off on this server/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create account" })).not.toBeInTheDocument();
  });

  it("shows the API's message when there have been too many attempts", async () => {
    mode("open");
    api.routes["POST /api/v1/auth/sign-up"] = { status: 429, body: { detail: "Too many attempts. Try again in 1 hour." } };
    const { user } = renderUI(<SignUpScreen inviteToken={null} />);

    await user.type(await screen.findByLabelText("Your name"), "Zara");
    await user.type(screen.getByLabelText("Work email"), "zara@example.com");
    await user.type(screen.getByLabelText("Password"), "long-enough");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts. Try again in 1 hour.");
  });
});
