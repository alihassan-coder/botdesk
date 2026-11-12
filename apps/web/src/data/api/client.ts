/**
 * The one way the web app talks to apps/api. Sends the session cookie with every
 * request and turns the API's error answers into an `ApiError` whose message can be
 * shown to people as is.
 */

/** Where the API lives, e.g. http://localhost:8000. Empty means "no API: use the mock". */
export function apiBaseUrl(): string {
  // Written out in full so Next can inline it into the browser bundle at build time.
  return (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/+$/, "");
}

export class ApiError extends Error {
  /** HTTP status; 0 when the API couldn't be reached at all. */
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const UNREACHABLE = "Can't reach botdesk right now. Check your connection and try again.";
const SERVER_TROUBLE = "Something went wrong on our side. Try again in a moment.";

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
}

export async function apiFetch<T>(path: string, { method = "GET", body }: RequestOptions = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, {
      method,
      credentials: "include",
      ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
    });
  } catch {
    throw new ApiError(0, UNREACHABLE);
  }

  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => undefined);
  if (!response.ok) throw new ApiError(response.status, errorMessage(data));
  return data as T;
}

/** FastAPI answers `{detail: "message"}`, or `{detail: [...]}` for invalid input (422). */
function errorMessage(data: unknown): string {
  const detail = (data as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) return detail.map(describeProblem).join(" ");
  return SERVER_TROUBLE;
}

interface ValidationProblem {
  loc?: (string | number)[];
  msg?: string;
}

/** {loc: ["body", "password"], msg: "String should …"} → "Password: String should …." */
function describeProblem({ loc = [], msg = "Invalid value" }: ValidationProblem): string {
  const field = String(loc.at(-1) ?? "");
  const label = field && field !== "body" ? `${field.charAt(0).toUpperCase()}${field.slice(1)}: ` : "";
  return `${label}${msg.replace(/\.$/, "")}.`;
}
