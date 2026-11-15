import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderUI } from "@/test/render";
import { withFakeApi } from "@/test/fake-api";
import { ForgotPasswordScreen } from "./forgot-password-screen";

describe("ForgotPasswordScreen on the API", () => {
  const api = withFakeApi();

  it("shows the API's message when there have been too many requests", async () => {
    api.routes["POST /api/v1/auth/forgot-password"] = { status: 429, body: { detail: "Too many attempts. Try again in 1 hour." } };
    const { user } = renderUI(<ForgotPasswordScreen />);

    await user.type(screen.getByLabelText("Email"), "zara@example.com");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts. Try again in 1 hour.");
  });
});
