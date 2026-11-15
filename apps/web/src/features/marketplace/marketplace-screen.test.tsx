import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderUI } from "@/test/render";
import { signInOnApi, withFakeApi } from "@/test/fake-api";
import { MarketplaceScreen } from "./marketplace-screen";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

describe("Marketplace in the demo", () => {
  it("shows how often each template was hired", () => {
    renderUI(<MarketplaceScreen />);
    expect(screen.getByText("12.4k hires")).toBeInTheDocument();
  });
});

describe("Marketplace on the API", () => {
  withFakeApi();

  it("doesn't show made-up hire counts, and says templates are starting points", async () => {
    await signInOnApi();
    renderUI(<MarketplaceScreen />);
    expect(screen.getByRole("button", { name: "Hire Inbox Zero" })).toBeInTheDocument();
    expect(screen.queryByText(/hires$/)).not.toBeInTheDocument();
    expect(screen.getByText(/Templates are starting points/)).toBeInTheDocument();
  });
});
