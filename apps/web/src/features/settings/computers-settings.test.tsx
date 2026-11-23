import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { actions } from "@/data/store";
import { renderUI } from "@/test/render";
import { signInOnApi, withFakeApi } from "@/test/fake-api";
import { ComputersSettings } from "./computers-settings";

const storage = () => within(screen.getByRole("region", { name: "Storage" }));
const browser = () => within(screen.getByRole("region", { name: "Browser" }));

describe("ComputersSettings in the demo", () => {
  it("shows where files go now, the folder layout, and where browsers run", () => {
    renderUI(<ComputersSettings />);
    expect(storage().getByText("On this BotDesk server.")).toBeInTheDocument();
    expect(storage().getByText(/Each bot gets a folder named after it inside/)).toHaveTextContent("botdesk/, plus _shared for files every bot can read.");
    expect(browser().getByText("On this BotDesk server.")).toBeInTheDocument();
  });

  it("owners and admins switch to an S3-compatible bucket, with what's missing said first", async () => {
    const { user } = renderUI(<ComputersSettings />);
    await user.click(storage().getByRole("button", { name: "Change" }));
    await user.click(screen.getByRole("radio", { name: /S3-compatible/ }));
    expect(screen.getByText(/BotDesk is free; storage is billed by the provider you choose\. Local is free\./)).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "Cloudflare R2" }));
    expect(screen.getByRole("link", { name: "Cloudflare R2 pricing" })).toHaveAttribute("target", "_blank");
    await user.click(screen.getByRole("button", { name: "Check and save" }));
    expect(screen.getByText("Cloudflare R2 needs its endpoint, like https://<account-id>.r2.cloudflarestorage.com.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Endpoint"), "https://abc.r2.cloudflarestorage.com");
    await user.type(screen.getByLabelText("Region"), "auto");
    await user.type(screen.getByLabelText("Bucket"), "acme-files");
    await user.type(screen.getByLabelText("Access key ID"), "AKIA0000ABCD");
    await user.type(screen.getByLabelText("Secret access key"), "s3cret-value");
    await user.click(screen.getByRole("button", { name: "Check and save" }));

    expect(await storage().findByText("S3-compatible")).toBeInTheDocument();
    expect(storage().getByText("abc.r2.cloudflarestorage.com / acme-files")).toBeInTheDocument();
    expect(storage().getByText(/Key ••••ABCD/)).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Change storage" })).not.toBeInTheDocument();
  });

  it("owners and admins move bots' browsers to a cloud provider, with the provider's refusal shown", async () => {
    const { user } = renderUI(<ComputersSettings />);
    await user.click(browser().getByRole("button", { name: "Change" }));
    await user.click(browser().getByRole("radio", { name: /Steel/ }));
    expect(browser().getByRole("link", { name: "Steel pricing" })).toHaveAttribute("href", "https://steel.dev/pricing");
    expect(browser().getByText("BotDesk is free; browser time is billed by the provider you choose. Local is free.")).toBeInTheDocument();
    await user.click(browser().getByRole("button", { name: "Check and save" }));
    expect(browser().getByText("Paste your Steel API key.")).toBeInTheDocument();

    await user.type(browser().getByLabelText("API key"), "bad-key-123456");
    await user.click(browser().getByRole("button", { name: "Check and save" }));
    expect(await browser().findByRole("alert")).toHaveTextContent("The provider refused the key: 401 Unauthorized.");

    await user.clear(browser().getByLabelText("API key"));
    await user.type(browser().getByLabelText("API key"), "ste_live_1234ABCD");
    await user.click(browser().getByRole("button", { name: "Check and save" }));
    expect(await browser().findByText("Steel")).toBeInTheDocument();
    expect(browser().getByText(/Key ••••ABCD/)).toBeInTheDocument();
  });

  it("members see where files go and browsers run, but can't change either", async () => {
    await actions.changeMemberRole("u_me", "member");
    renderUI(<ComputersSettings />);
    expect(storage().getByText("On this BotDesk server.")).toBeInTheDocument();
    expect(storage().queryByRole("button", { name: "Change" })).not.toBeInTheDocument();
    expect(storage().getByText("Only owners and admins can change where files go.")).toBeInTheDocument();
    expect(browser().queryByRole("button", { name: "Change" })).not.toBeInTheDocument();
    expect(browser().getByText("Only owners and admins can change where browsers run.")).toBeInTheDocument();
  });
});

describe("ComputersSettings on the API", () => {
  const api = withFakeApi();

  it("shows the API's reason when the bucket doesn't work, and keeps the form open", async () => {
    api.routes["GET /api/v1/orgs/o1/storage"] = {
      status: 200,
      body: { provider: "s3", s3: { endpoint: "", region: "us-east-1", bucket: "acme", prefix: "botdesk-files", accessKeyHint: "WXYZ" }, localAvailable: true, checkedAt: "2026-11-23T08:00:00Z" },
    };
    api.routes["PUT /api/v1/orgs/o1/storage"] = { status: 400, body: { detail: "The bucket said no: AccessDenied (403)." } };
    await signInOnApi();
    const { user } = renderUI(<ComputersSettings />);
    expect(await storage().findByText("AWS / acme/botdesk-files")).toBeInTheDocument();

    await user.click(storage().getByRole("button", { name: "Change" }));
    await user.type(screen.getByLabelText("Access key ID"), "AKIA1111WXYZ");
    await user.click(screen.getByRole("button", { name: "Check and save" }));

    expect(await screen.findByText("The bucket said no: AccessDenied (403).")).toHaveAttribute("role", "alert");
    expect(screen.getByRole("form", { name: "Change storage" })).toBeInTheDocument();
    // The saved secret is kept: it isn't sent again.
    expect(api.sent.find((s) => s.key === "PUT /api/v1/orgs/o1/storage")?.body).toEqual({
      provider: "s3", s3: { endpoint: "", region: "us-east-1", bucket: "acme", prefix: "botdesk-files", accessKeyId: "AKIA1111WXYZ" },
    });
  });

  it("keeps the saved browser key when it's left empty, and shows the provider's refusal", async () => {
    api.routes["GET /api/v1/orgs/o1/browser-provider"] = {
      status: 200, body: { provider: "browserbase", keyHint: "WXYZ", projectId: "proj_1", localAvailable: true, checkedAt: "2026-11-23T08:00:00Z" },
    };
    api.routes["PUT /api/v1/orgs/o1/browser-provider"] = { status: 400, body: { detail: "Browserbase said no: your plan's browser hours are used up." } };
    await signInOnApi();
    const { user } = renderUI(<ComputersSettings />);
    expect(await browser().findByText("Browserbase")).toBeInTheDocument();
    expect(browser().getByText(/Key ••••WXYZ/)).toBeInTheDocument();

    await user.click(browser().getByRole("button", { name: "Change" }));
    expect(browser().getByLabelText("Project ID (optional)")).toHaveValue("proj_1");
    await user.click(browser().getByRole("button", { name: "Check and save" }));

    expect(await browser().findByText("Browserbase said no: your plan's browser hours are used up.")).toHaveAttribute("role", "alert");
    expect(api.sent.find((s) => s.key === "PUT /api/v1/orgs/o1/browser-provider")?.body).toEqual({ provider: "browserbase", projectId: "proj_1" });
  });
});
