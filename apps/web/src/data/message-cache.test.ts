import { describe, expect, it, vi } from "vitest";
import { CACHE_LIMITS, createMessageCache, newestToKeep, openIndexedDb, type CachedChat, type ChatStore } from "./message-cache";
import type { Message } from "./types";

const message = (id: string, patch: Partial<Message> = {}): Message => ({
  id, threadId: "t1", author: { type: "user", id: "u1" }, parts: [{ type: "text", text: `Message ${id}` }], createdAt: "2026-11-26T10:00:00Z", ...patch,
});
const chat = (threadId: string, userId = "u1", orgId = "o1") => ({ userId, orgId, threadId });

/** IndexedDB's stand-in: chats in a Map, in the order they were saved. */
function memoryStore(): ChatStore & { chats: Map<string, CachedChat> } {
  const chats = new Map<string, CachedChat>();
  return {
    chats,
    get: async (key) => chats.get(key),
    put: async (c) => {
      chats.delete(key(c));
      chats.set(key(c), c);
    },
    keysByAge: async () => [...chats.values()].sort((a, b) => a.savedAt - b.savedAt).map((c) => c.key),
    remove: async (keys) => keys.forEach((k) => chats.delete(k)),
    clear: async () => chats.clear(),
  };
}
const key = (c: CachedChat) => c.key;

describe("the message cache", () => {
  it("saves a chat's messages and reads them back, for that person in that organization only", async () => {
    const cache = createMessageCache(async () => memoryStore());
    await cache.save(chat("t1"), [message("m1"), message("m2")]);

    expect((await cache.read(chat("t1"))).map((m) => m.id)).toEqual(["m1", "m2"]);
    expect(await cache.read(chat("t2"))).toEqual([]);
    expect(await cache.read(chat("t1", "u2"))).toEqual([]);
    expect(await cache.read(chat("t1", "u1", "o2"))).toEqual([]);
  });

  it("keeps the newest 50 saved messages, not ones still on their way or being written", () => {
    const many = Array.from({ length: 60 }, (_, i) => message(`m${i}`));
    const kept = newestToKeep([...many, message("local-1"), message("typing-r1"), message("r2", { status: "streaming" })]);
    expect(kept).toHaveLength(50);
    expect(kept[0].id).toBe("m10");
    expect(kept.at(-1)?.id).toBe("m59");
  });

  it("keeps a chat small: the newest messages that fit", () => {
    const long = (id: string) => message(id, { parts: [{ type: "text", text: "x".repeat(400) }] });
    const kept = newestToKeep([long("m1"), long("m2"), long("m3")], { ...CACHE_LIMITS, bytesPerChat: 1200 });
    expect(kept.map((m) => m.id)).toEqual(["m2", "m3"]);
  });

  it("keeps only the 20 chats saved most recently", async () => {
    const store = memoryStore();
    const cache = createMessageCache(async () => store);
    const clock = vi.spyOn(Date, "now");
    for (let i = 0; i <= 20; i++) {
      clock.mockReturnValue(1000 + i);
      await cache.save(chat(`t${i}`), [message("m1")]);
    }
    clock.mockRestore();

    expect(store.chats.size).toBe(20);
    expect(await cache.read(chat("t0"))).toEqual([]);
    expect(await cache.read(chat("t20"))).toHaveLength(1);
  });

  it("clear forgets every chat, even one whose save started just before", async () => {
    const store = memoryStore();
    const cache = createMessageCache(async () => store);
    await cache.save(chat("t1"), [message("m1")]);
    const late = cache.save(chat("t2"), [message("m2")]);
    await cache.clear();
    await late;

    expect(store.chats.size).toBe(0);
    expect(await cache.read(chat("t1"))).toEqual([]);
  });

  it("carries on as if nothing was kept when storage fails", async () => {
    const broken: ChatStore = {
      get: () => Promise.reject(new Error("QuotaExceededError")),
      put: () => Promise.reject(new Error("QuotaExceededError")),
      keysByAge: () => {
        throw new Error("InvalidStateError");
      },
      remove: () => Promise.reject(new Error("InvalidStateError")),
      clear: () => Promise.reject(new Error("InvalidStateError")),
    };
    for (const open of [async () => broken, async () => null, () => Promise.reject(new Error("SecurityError"))]) {
      const cache = createMessageCache(open);
      await expect(cache.save(chat("t1"), [message("m1")])).resolves.toBeUndefined();
      await expect(cache.read(chat("t1"))).resolves.toEqual([]);
      await expect(cache.clear()).resolves.toBeUndefined();
    }
  });

  it("has nowhere to keep anything where the browser has no IndexedDB", async () => {
    // jsdom has none, like some locked-down browsers.
    await expect(openIndexedDb()).resolves.toBeNull();
  });
});
