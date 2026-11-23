import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { actions } from "@/data/store";
import { renderUI } from "@/test/render";
import { signInOnApi, withFakeApi } from "@/test/fake-api";
import { ComputersSettings } from "./computers-settings";

const storage = () => within(screen.getByRole("region", { name: "Storage" }));

describe("ComputersSettings in the demo", () => {
  it("shows where files go now, the folder layout, and where browsers run", () => {
    renderUI(<ComputersSettings />);
    expect(storage().getByText("On this BotDesk server.")).toBeInTheDocument();
    expect(storage().getByText(/Each bot gets a folder named after it inside/)).toHaveTextContent("botdesk/, plus _shared for files every bot can read.");
    expect(within(screen.getByRole("region", { name: "Browser" })).getByText(/Each bot has its own browser on this BotDesk server/)).toBeInTheDocument();
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

  it("members see where files go but can't change it", async () => {
    await actions.changeMemberRole("u_me", "member");
    renderUI(<ComputersSettings />);
    expect(storage().getByText("On this BotDesk server.")).toBeInTheDocument();
    expect(storage().queryByRole("button", { name: "Change" })).not.toBeInTheDocument();
    expect(storage().getByText("Only owners and admins can change where files go.")).toBeInTheDocument();
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
});
