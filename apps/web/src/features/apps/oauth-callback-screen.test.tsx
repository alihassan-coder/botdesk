import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderUI } from "@/test/render";
import { OAuthCallbackScreen } from "./oauth-callback-screen";

describe("The OAuth callback page", () => {
  it("says the account is connected, with a way back to Connect apps", () => {
    renderUI(<OAuthCallbackScreen result="connected" code={null} connector="gmail" />);
    expect(screen.getByText("Connected", { selector: "[data-slot=alert-title]" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Connect apps" })).toHaveAttribute("href", "/apps");
  });

  it("says why nothing was connected when the person cancelled", () => {
    renderUI(<OAuthCallbackScreen result="error" code="denied" connector={null} />);
    expect(screen.getByText("Not connected")).toBeInTheDocument();
    expect(screen.getByText("You cancelled signing in, so nothing was connected.")).toBeInTheDocument();
  });

  it("explains an expired or reused sign-in", () => {
    renderUI(<OAuthCallbackScreen result="error" code="expired" connector={null} />);
    expect(screen.getByText(/took too long or was already used/)).toBeInTheDocument();
  });

  it("shows the generic message for a code it doesn't know, never the code itself", () => {
    renderUI(<OAuthCallbackScreen result="error" code="provider_said_<b>no</b>" connector={null} />);
    expect(screen.getByText("Couldn't finish connecting the app. Try again.")).toBeInTheDocument();
    expect(screen.queryByText(/provider_said/)).not.toBeInTheDocument();
  });
});
