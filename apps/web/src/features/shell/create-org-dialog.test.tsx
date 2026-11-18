import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { apiOrg, signInOnApi, withFakeApi } from "@/test/fake-api";
import { CreateOrgDialog } from "./create-org-dialog";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const acme = { ...apiOrg, id: "o2", name: "Acme Labs", slug: "acme-labs" };

describe("Create organization, on the API", () => {
  const api = withFakeApi();

  it("creates the organization, makes you its owner and switches to it", async () => {
    await signInOnApi();
    api.routes["POST /api/v1/orgs"] = { status: 201, body: acme };
    api.routes["GET /api/v1/orgs/o2/members"] = { status: 200, body: [{ id: "u1", name: "Zara", email: "zara@example.com", handle: "zara", role: "owner" }] };
    api.routes["GET /api/v1/orgs/o2/bots"] = { status: 200, body: [] };
    api.routes["GET /api/v1/orgs/o2/threads"] = { status: 200, body: [] };
    const onOpenChange = vi.fn();
    const { user } = renderUI(<CreateOrgDialog open onOpenChange={onOpenChange} />);

    await user.type(screen.getByLabelText("Name"), "Acme Labs");
    await user.click(screen.getByRole("button", { name: "Create organization" }));

    await vi.waitFor(() => expect(getStoreSnapshot().org.id).toBe("o2"));
    expect(api.sent.find((r) => r.key === "POST /api/v1/orgs")?.body).toEqual({ name: "Acme Labs" });
    expect(getStoreSnapshot().orgs.map((o) => [o.name, o.role])).toEqual([["Zara's team", "owner"], ["Acme Labs", "owner"]]);
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(push).toHaveBeenCalledWith("/");
  });

  it("shows the API's refusal and stays where you are", async () => {
    await signInOnApi();
    api.routes["POST /api/v1/orgs"] = { status: 400, body: { detail: "Give the organization a name." } };
    const { user } = renderUI(<CreateOrgDialog open onOpenChange={vi.fn()} />);

    await user.type(screen.getByLabelText("Name"), "!");
    await user.click(screen.getByRole("button", { name: "Create organization" }));

    expect(await screen.findByText("Give the organization a name.")).toBeInTheDocument();
    expect(getStoreSnapshot().org.id).toBe("o1");
  });
});

describe("Create organization, in the demo", () => {
  it("asks for an account instead", async () => {
    const { user } = renderUI(<CreateOrgDialog open onOpenChange={vi.fn()} />);
    await user.type(screen.getByLabelText("Name"), "Acme Labs");
    await user.click(screen.getByRole("button", { name: "Create organization" }));
    expect(await screen.findByText("Creating organizations needs an account. Sign up to make your own.")).toBeInTheDocument();
  });
});
