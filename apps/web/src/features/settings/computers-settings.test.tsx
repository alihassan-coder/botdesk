import { screen, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { actions } from "@/data/store";
import { renderUI } from "@/test/render";
import { signInOnApi, withFakeApi } from "@/test/fake-api";
import { ComputersSettings } from "./computers-settings";

const storage = () => within(screen.getByRole("region", { name: "Storage" }));
const browser = () => within(screen.getByRole("region", { name: "Browser" }));

/**
 * Fills a field with one paste instead of a key press per character, so these long forms stay well
 * inside the test timeout on a slow CI runner. Every query below is scoped to its card, so nothing
 * can reach into the other card's form.
 */
async function fill(user: UserEvent, field: HTMLElement, text: string) {
  await user.clear(field);
  await user.paste(text);
}

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
    await user.click(storage().getByRole("radio", { name: /S3-compatible/ }));
    expect(storage().getByText(/BotDesk is free; storage is billed by the provider you choose\. Local is free\./)).toBeInTheDocument();

    await user.click(storage().getByRole("radio", { name: "Cloudflare R2" }));
    expect(await storage().findByRole("link", { name: "Cloudflare R2 pricing" })).toHaveAttribute("target", "_blank");
    await user.click(storage().getByRole("button", { name: "Check and save" }));
    expect(storage().getByText("Cloudflare R2 needs its endpoint, like https://<account-id>.r2.cloudflarestorage.com.")).toBeInTheDocument();

    await fill(user, storage().getByLabelText("Endpoint"), "https://abc.r2.cloudflarestorage.com");
    await fill(user, storage().getByLabelText("Region"), "auto");
    await fill(user, storage().getByLabelText("Bucket"), "acme-files");
    await fill(user, storage().getByLabelText("Access key ID"), "AKIA0000ABCD");
    await fill(user, storage().getByLabelText("Secret access key"), "s3cret-value");
    await user.click(storage().getByRole("button", { name: "Check and save" }));

    expect(await storage().findByText("S3-compatible")).toBeInTheDocument();
    expect(storage().getByText("abc.r2.cloudflarestorage.com / acme-files")).toBeInTheDocument();
    expect(storage().getByText(/Key ••••ABCD/)).toBeInTheDocument();
    expect(storage().queryByRole("form", { name: "Change storage" })).not.toBeInTheDocument();
  });

  it("owners and admins move bots' browsers to a cloud provider, with the provider's refusal shown", async () => {
    const { user } = renderUI(<ComputersSettings />);
    await user.click(browser().getByRole("button", { name: "Change" }));
    const steel = browser().getByRole("radio", { name: /Steel/ });
    await user.click(steel);
    expect(steel).toBeChecked();
    // The pricing link shows once Steel is picked, as a person would see it.
    expect(await browser().findByRole("link", { name: "Steel pricing" })).toHaveAttribute("href", "https://steel.dev/pricing");
    expect(browser().getByText("BotDesk is free; browser time is billed by the provider you choose. Local is free.")).toBeInTheDocument();
    await user.click(browser().getByRole("button", { name: "Check and save" }));
    expect(browser().getByText("Paste your Steel API key.")).toBeInTheDocument();

    await fill(user, browser().getByLabelText("API key"), "bad-key-123456");
    await user.click(browser().getByRole("button", { name: "Check and save" }));
    expect(await browser().findByRole("alert")).toHaveTextContent("The provider refused the key: 401 Unauthorized.");

    await fill(user, browser().getByLabelText("API key"), "ste_live_1234ABCD");
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
    await fill(user, storage().getByLabelText("Access key ID"), "AKIA1111WXYZ");
    await user.click(storage().getByRole("button", { name: "Check and save" }));

    expect(await storage().findByText("The bucket said no: AccessDenied (403).")).toHaveAttribute("role", "alert");
    expect(storage().getByRole("form", { name: "Change storage" })).toBeInTheDocument();
    // The saved secret is kept: it isn't sent again.
    expect(api.sent.find((s) => s.key === "PUT /api/v1/orgs/o1/storage")?.body).toEqual({
      provider: "s3", s3: { endpoint: "", region: "us-east-1", bucket: "acme", prefix: "botdesk-files", accessKeyId: "AKIA1111WXYZ" },
    });
  });

  it("switches storage to Cloudinary, sending the cloud name, key and secret", async () => {
    api.routes["GET /api/v1/orgs/o1/storage"] = { status: 200, body: { provider: "local", s3: null, cloudinary: null, localAvailable: true, checkedAt: null } };
    api.routes["PUT /api/v1/orgs/o1/storage"] = {
      status: 200, body: { provider: "cloudinary", s3: null, cloudinary: { cloudName: "acme", apiKeyHint: "9012" }, localAvailable: true, checkedAt: "2026-11-23T08:00:00Z" },
    };
    await signInOnApi();
    const { user } = renderUI(<ComputersSettings />);
    await user.click(await storage().findByRole("button", { name: "Change" }));
    await user.click(storage().getByRole("radio", { name: /Cloudinary/ }));
    expect(await storage().findByRole("link", { name: "Cloudinary pricing" })).toHaveAttribute("href", "https://cloudinary.com/pricing");
    await fill(user, storage().getByLabelText("Cloud name"), "acme");
    await fill(user, storage().getByLabelText("API key"), "123456789012");
    await fill(user, storage().getByLabelText("API secret"), "s3cret-value");
    await user.click(storage().getByRole("button", { name: "Check and save" }));

    expect(await storage().findByText("· acme")).toBeInTheDocument();
    expect(storage().getByText(/Key ••••9012/)).toBeInTheDocument();
    expect(api.sent.find((s) => s.key === "PUT /api/v1/orgs/o1/storage")?.body).toEqual({
      provider: "cloudinary", cloudinary: { cloudName: "acme", apiKey: "123456789012", apiSecret: "s3cret-value" },
    });
  });

  it("keeps Cloudinary's saved secret when it's left empty, and shows Cloudinary's refusal", async () => {
    api.routes["GET /api/v1/orgs/o1/storage"] = {
      status: 200, body: { provider: "cloudinary", s3: null, cloudinary: { cloudName: "acme", apiKeyHint: "9012" }, localAvailable: true, checkedAt: "2026-11-23T08:00:00Z" },
    };
    api.routes["PUT /api/v1/orgs/o1/storage"] = { status: 400, body: { detail: "Cloudinary refused the keys for acme. Check the API key and secret." } };
    await signInOnApi();
    const { user } = renderUI(<ComputersSettings />);
    await user.click(await storage().findByRole("button", { name: "Change" }));
    expect(storage().getByLabelText("Cloud name")).toHaveValue("acme");
    await fill(user, storage().getByLabelText("API key"), "123456789012");
    await user.click(storage().getByRole("button", { name: "Check and save" }));

    expect(await storage().findByText("Cloudinary refused the keys for acme. Check the API key and secret.")).toHaveAttribute("role", "alert");
    expect(api.sent.find((s) => s.key === "PUT /api/v1/orgs/o1/storage")?.body).toEqual({
      provider: "cloudinary", cloudinary: { cloudName: "acme", apiKey: "123456789012" },
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
