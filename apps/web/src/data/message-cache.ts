import type { Message } from "./types";

/*
 * Recent messages kept on this device, so a chat opens at once after a reload (API mode only; the
 * store decides when). The newest 50 messages of the last 20 chats, in IndexedDB, keyed by person,
 * organization and chat. Anything here may fail (a private window, storage turned off, a full disk,
 * another tab upgrading the database): then it's as if nothing was kept, and the chat waits for the
 * API as before. Only store.ts uses this.
 */

export const CACHE_LIMITS = { chats: 20, messagesPerChat: 50, bytesPerChat: 200_000 };
type Limits = typeof CACHE_LIMITS;

/** One chat as kept: its newest messages, and when, so the oldest chat can make room. */
export interface CachedChat {
  key: string;
  savedAt: number;
  messages: Message[];
}

/** Where cached chats are kept (IndexedDB in the browser). Any call may throw or reject. */
export interface ChatStore {
  get(key: string): Promise<CachedChat | undefined>;
  put(chat: CachedChat): Promise<void>;
  /** Every key, the chat saved longest ago first. */
  keysByAge(): Promise<string[]>;
  remove(keys: string[]): Promise<void>;
  clear(): Promise<void>;
}

export interface ChatKey {
  userId: string;
  orgId: string;
  threadId: string;
}

const keyOf = ({ userId, orgId, threadId }: ChatKey) => `${userId}/${orgId}/${threadId}`;

/** Saved messages only: not yours still on its way, a reply still being written, or a typing stand-in. */
const isSaved = (m: Message) => m.status !== "streaming" && !m.id.startsWith("local-") && !m.id.startsWith("typing-");

/** The newest saved messages that fit: at most 50, in about 200 KB. Oldest first, like the chat. */
export function newestToKeep(messages: Message[], limits: Limits = CACHE_LIMITS): Message[] {
  const kept: Message[] = [];
  let size = 0;
  for (let i = messages.length - 1; i >= 0 && kept.length < limits.messagesPerChat; i--) {
    if (!isSaved(messages[i])) continue;
    size += JSON.stringify(messages[i]).length;
    if (size > limits.bytesPerChat) break;
    kept.push(messages[i]);
  }
  return kept.reverse();
}

export type MessageCache = ReturnType<typeof createMessageCache>;

/** The cache, over whatever `open` gives (null: there's nowhere to keep anything). */
export function createMessageCache(open: () => Promise<ChatStore | null>, limits: Limits = CACHE_LIMITS) {
  let opening: Promise<ChatStore | null> | null = null;
  const store = () => (opening ??= open().catch(() => null));
  /** Bumped by clear(), so a save that started before it can't bring a chat back. */
  let generation = 0;

  return {
    /** The chat's messages kept here, or none. */
    async read(chat: ChatKey): Promise<Message[]> {
      try {
        const found = await (await store())?.get(keyOf(chat));
        return Array.isArray(found?.messages) ? found.messages : [];
      } catch {
        return [];
      }
    },

    /** Keep the chat's newest messages, and only the 20 chats saved most recently. */
    async save(chat: ChatKey, messages: Message[]): Promise<void> {
      const started = generation;
      try {
        const s = await store();
        if (!s || started !== generation) return;
        const kept = newestToKeep(messages, limits);
        if (kept.length === 0) return await s.remove([keyOf(chat)]);
        await s.put({ key: keyOf(chat), savedAt: Date.now(), messages: kept });
        const keys = await s.keysByAge();
        if (keys.length > limits.chats) await s.remove(keys.slice(0, keys.length - limits.chats));
      } catch {
        // Nowhere to keep it: the next opening waits for the API.
      }
    },

    /** Forget every chat (signing out, switching organization). */
    async clear(): Promise<void> {
      generation++;
      try {
        await (await store())?.clear();
      } catch {
        // Nothing could be kept either, then.
      }
    },
  };
}

const DB_NAME = "botdesk-cache";
const CHATS = "chats";

function done<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/** IndexedDB, opened the first time it's needed. None where the browser has none (or won't open it). */
export async function openIndexedDb(): Promise<ChatStore | null> {
  if (typeof indexedDB === "undefined") return null;
  const request = indexedDB.open(DB_NAME, 1);
  request.onupgradeneeded = () => request.result.createObjectStore(CHATS, { keyPath: "key" }).createIndex("savedAt", "savedAt");
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error("The message cache is open in an older tab."));
  });
  // A newer version in another tab: step aside (calls after this fail, and the cache is skipped).
  db.onversionchange = () => db.close();
  const chats = (mode: IDBTransactionMode) => db.transaction(CHATS, mode).objectStore(CHATS);

  return {
    get: (key) => done(chats("readonly").get(key)) as Promise<CachedChat | undefined>,
    put: async (chat) => void (await done(chats("readwrite").put(chat))),
    keysByAge: async () => (await done(chats("readonly").index("savedAt").getAllKeys())).map(String),
    remove: async (keys) => {
      const store = chats("readwrite");
      await Promise.all(keys.map((key) => done(store.delete(key))));
    },
    clear: async () => void (await done(chats("readwrite").clear())),
  };
}

export const messageCache = createMessageCache(openIndexedDb);
