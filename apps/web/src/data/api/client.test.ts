import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch } from "./client";

/** A fake fetch that answers once with this status and JSON body (or no body). */
function answer(status: number, body?: unknown) {
  const fetchMock = vi.fn(async () =>
    body === undefined ? new Response(null, { status }) : Response.json(body, { status }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("apiFetch", () => {
  it("calls the API at NEXT_PUBLIC_API_URL with the session cookie and a JSON body", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test/");
    const fetchMock = answer(200, { ok: 1 });

    await expect(apiFetch("/api/v1/auth/sign-in", { method: "POST", body: { email: "a@b.co" } })).resolves.toEqual({ ok: 1 });

    expect(fetchMock).toHaveBeenCalledWith("http://api.test/api/v1/auth/sign-in", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: "a@b.co" }),
    });
  });

  it("returns undefined for 204 No Content", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
    answer(204);
    await expect(apiFetch("/api/v1/auth/sign-out", { method: "POST" })).resolves.toBeUndefined();
  });

  it("turns {detail} into an ApiError with the API's message and status", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
    answer(401, { detail: "That email and password don't match." });

    const error = await apiFetch("/api/v1/auth/sign-in").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 401, message: "That email and password don't match." });
  });

  it("joins a 422 validation list into one readable message", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
    answer(422, {
      detail: [
        { type: "string_too_short", loc: ["body", "name"], msg: "String should have at least 1 character" },
        { type: "string_too_short", loc: ["body", "password"], msg: "String should have at least 8 characters" },
      ],
    });

    await expect(apiFetch("/x")).rejects.toMatchObject({
      status: 422,
      message: "Name: String should have at least 1 character. Password: String should have at least 8 characters.",
    });
  });

  it("gives a plain message when the API can't be reached or answers without JSON", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    await expect(apiFetch("/x")).rejects.toMatchObject({ status: 0, message: "Can't reach botdesk right now. Check your connection and try again." });

    answer(500);
    await expect(apiFetch("/x")).rejects.toMatchObject({ status: 500, message: "Something went wrong on our side. Try again in a moment." });
  });
});
