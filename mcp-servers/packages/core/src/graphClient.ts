import type { TokenCredential } from "@azure/identity";

export const GRAPH_BASE = "https://graph.microsoft.com/v1.0";
export const GRAPH_DEFAULT_SCOPE = "https://graph.microsoft.com/.default";

/** Bounded retry budget for 429 (throttling). Graph throttles routinely in real
 * tenants -- dying on the first 429 makes a tool unusable, but retrying forever
 * risks hanging a caller, so this caps both attempts and the wait per attempt. */
const MAX_RETRY_ATTEMPTS = 3;
const MAX_RETRY_WAIT_MS = 30_000;

export class GraphApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown, url: string) {
    super(`Graph API request to ${url} failed with status ${status}: ${describeBody(body)}`);
    this.name = "GraphApiError";
    this.status = status;
    this.body = body;
  }
}

function describeBody(body: unknown): string {
  if (typeof body === "string") return body.slice(0, 500);
  try {
    return JSON.stringify(body);
  } catch {
    return String(body);
  }
}

/**
 * Reads a response body without assuming it's JSON. Graph errors are normally
 * JSON, but a WAF, a proxy, or a plain 5xx from an intermediate hop can return
 * HTML or plain text -- JSON.parse on that throws SyntaxError and loses the
 * real status code inside a confusing secondary error. Falls back to the raw
 * text (truncated by describeBody above when it ends up in an error message).
 */
async function readBody(res: Response): Promise<unknown> {
  if (res.status === 204) return undefined;
  const text = await res.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function retryDelayMs(res: Response, attempt: number): number {
  const header = res.headers.get("retry-after");
  let ms = 1000 * 2 ** attempt; // exponential backoff fallback if the header is absent/unusable
  if (header) {
    const seconds = Number(header);
    if (Number.isFinite(seconds)) {
      ms = seconds * 1000;
    } else {
      const at = Date.parse(header);
      if (!Number.isNaN(at)) ms = at - Date.now();
    }
  }
  if (!Number.isFinite(ms) || ms < 0) ms = 1000 * 2 ** attempt;
  return Math.min(ms, MAX_RETRY_WAIT_MS);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export interface GraphRequestOptions {
  query?: Record<string, string | number | undefined>;
  body?: unknown;
  /** Extra scopes for the token request. Defaults to the Graph .default scope. */
  scopes?: string[];
}

export interface GraphPage<T> {
  items: T[];
  /** True when the page cap (maxPages) was hit while @odata.nextLink still had
   * more to fetch -- the caller has less than the full result set and should
   * say so rather than presenting it as complete. */
  truncated: boolean;
}

/**
 * Minimal typed wrapper over fetch() for Microsoft Graph. Deliberately does
 * not pull in the full @microsoft/microsoft-graph-client SDK -- these
 * servers only ever touch a couple dozen endpoints each, and a thin client
 * is easier to mock offline in tests (see test/graphClient.test.ts).
 */
export class GraphClient {
  constructor(
    private readonly credential: TokenCredential,
    private readonly baseUrl: string = GRAPH_BASE,
    /** Scopes used when a call doesn't pass its own. App-only clients keep the
     * .default scope; delegated (device code) clients pass the specific
     * Graph permissions they need at construction time. */
    private readonly defaultScopes: string[] = [GRAPH_DEFAULT_SCOPE]
  ) {}

  private async getToken(scopes: string[]): Promise<string> {
    const token = await this.credential.getToken(scopes);
    if (!token) {
      throw new Error("Failed to acquire a Graph access token (credential.getToken returned null).");
    }
    return token.token;
  }

  private buildUrl(path: string, query?: GraphRequestOptions["query"]): string {
    const url = path.startsWith("http") ? new URL(path) : new URL(this.baseUrl + path);
    if (query) {
      for (const [key, value] of Object.entries(query)) {
        if (value !== undefined) url.searchParams.set(key, String(value));
      }
    }
    return url.toString();
  }

  /** fetch() with a bounded 429 retry, honoring Retry-After when Graph sends one. */
  private async fetchWithRetry(url: string, init: RequestInit): Promise<Response> {
    let attempt = 0;
    for (;;) {
      const res = await fetch(url, init);
      if (res.status === 429 && attempt < MAX_RETRY_ATTEMPTS) {
        await sleep(retryDelayMs(res, attempt));
        attempt += 1;
        continue;
      }
      return res;
    }
  }

  async request<T = unknown>(
    method: "GET" | "POST" | "PATCH" | "DELETE" | "PUT",
    path: string,
    options: GraphRequestOptions = {}
  ): Promise<T> {
    const scopes = options.scopes ?? this.defaultScopes;
    const token = await this.getToken(scopes);
    const url = this.buildUrl(path, options.query);

    const res = await this.fetchWithRetry(url, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });

    const parsed = await readBody(res);

    if (!res.ok) {
      throw new GraphApiError(res.status, parsed, url);
    }

    return parsed as T;
  }

  get<T = unknown>(path: string, options?: GraphRequestOptions): Promise<T> {
    return this.request<T>("GET", path, options);
  }
  /** WRITE. Callers must route this through core's assertWriteAllowed (env flag
   * + confirm:true) before calling -- this method performs no gating itself. */
  post<T = unknown>(path: string, options?: GraphRequestOptions): Promise<T> {
    return this.request<T>("POST", path, options);
  }
  /** WRITE. Callers must route this through core's assertWriteAllowed (env flag
   * + confirm:true) before calling -- this method performs no gating itself. */
  patch<T = unknown>(path: string, options?: GraphRequestOptions): Promise<T> {
    return this.request<T>("PATCH", path, options);
  }
  /** WRITE. Callers must route this through core's assertWriteAllowed (env flag
   * + confirm:true) before calling -- this method performs no gating itself. */
  put<T = unknown>(path: string, options?: GraphRequestOptions): Promise<T> {
    return this.request<T>("PUT", path, options);
  }
  /** WRITE/DESTRUCTIVE. Callers must route this through core's assertWriteAllowed
   * (env flag + confirm:true) before calling -- this method performs no gating
   * itself. */
  delete<T = unknown>(path: string, options?: GraphRequestOptions): Promise<T> {
    return this.request<T>("DELETE", path, options);
  }

  /** Follows @odata.nextLink until exhausted or maxPages is reached. Reports
   * truncation rather than silently returning a partial result as if it were
   * complete -- see GraphPage. */
  async getAllPages<T = unknown>(
    path: string,
    options: GraphRequestOptions & { maxPages?: number } = {}
  ): Promise<GraphPage<T>> {
    const maxPages = options.maxPages ?? 10;
    const items: T[] = [];
    let next: string | undefined = this.buildUrl(path, options.query);
    let page = 0;

    while (next && page < maxPages) {
      const scopes = options.scopes ?? this.defaultScopes;
      const token = await this.getToken(scopes);
      const res = await this.fetchWithRetry(next, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const parsed = await readBody(res);
      if (!res.ok) {
        throw new GraphApiError(res.status, parsed, next);
      }
      const body = (parsed ?? {}) as { value?: T[]; "@odata.nextLink"?: string };
      items.push(...(body.value ?? []));
      next = body["@odata.nextLink"];
      page += 1;
    }

    return { items, truncated: Boolean(next) && page >= maxPages };
  }
}
