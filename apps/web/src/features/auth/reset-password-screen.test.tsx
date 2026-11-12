import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderUI } from "@/test/render";
import { ResetPasswordScreen } from "./reset-password-screen";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, push: vi.fn() }) }));
const toastSuccess = vi.fn();
vi.mock("sonner", () => ({ toast: { success: (message: string) => toastSuccess(message) } }));

beforeEach(() => {
  replace.mockClear();
  toastSuccess.mockClear();
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("ResetPasswordScreen", () => {
  it("needs 8 characters, then sends you to sign in with a toast (mock mode pretends it worked)", async () => {
    const { user } = renderUI(<ResetPasswordScreen token="abc" />);
    const save = screen.getByRole("button", { name: "Set new password" });

    await user.type(screen.getByLabelText("New password"), "short");
    expect(save).toBeDisabled();
    await user.type(screen.getByLabelText("New password"), "-but-long-now");
    await user.click(save);

    await vi.waitFor(() => expect(replace).toHaveBeenCalledWith("/sign-in"));
    expect(toastSuccess).toHaveBeenCalledWith("Password changed. Sign in with your new password.");
  });

  it("posts the token and password to the API, and shows why an old link failed", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
    const fetchMock = vi.fn(async () =>
      Response.json({ detail: "This reset link has expired or was already used. Ask for a new one." }, { status: 400 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { user } = renderUI(<ResetPasswordScreen token="old-token" />);

    await user.type(screen.getByLabelText("New password"), "a-new-password");
    await user.click(screen.getByRole("button", { name: "Set new password" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("This reset link has expired or was already used.");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/api/v1/auth/reset-password");
    expect(JSON.parse(String(init.body))).toEqual({ token: "old-token", password: "a-new-password" });
    expect(replace).not.toHaveBeenCalled();
  });

  it("explains a link without a token", () => {
    renderUI(<ResetPasswordScreen token={null} />);
    expect(screen.getByRole("heading", { name: "This link isn't complete" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Get a new link" })).toHaveAttribute("href", "/forgot-password");
  });
});
