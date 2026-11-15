import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderUI } from "@/test/render";
import { withFakeApi } from "@/test/fake-api";
import { SignInScreen } from "./sign-in-screen";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), push: vi.fn() }) }));

describe("SignInScreen on the API", () => {
  const api = withFakeApi();
  const mode = (signUpMode: string) => (api.routes["GET /api/v1/auth/options"] = { status: 200, body: { signUpMode } });

  it("shows the API's message when there have been too many attempts", async () => {
    mode("open");
    api.routes["POST /api/v1/auth/sign-in"] = { status: 429, body: { detail: "Too many attempts. Try again in 1 minute." } };
    const { user } = renderUI(<SignInScreen />);

    await user.type(screen.getByLabelText("Email"), "zara@example.com");
    await user.type(screen.getByLabelText("Password"), "guess");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts. Try again in 1 minute.");
  });

  it("offers to create an account while sign-up is open", async () => {
    mode("open");
    renderUI(<SignInScreen />);
    expect(await screen.findByRole("link", { name: "Create an account" })).toHaveAttribute("href", "/sign-up");
  });

  it("hides it when sign-up is closed", async () => {
    mode("closed");
    renderUI(<SignInScreen />);
    expect(await screen.findByText("New accounts are turned off on this server. Ask your admin if you need one.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Create an account" })).not.toBeInTheDocument();
  });
});
