import type { TokenCredential } from "@azure/identity";

export const GRAPH_BASE = "https://graph.microsoft.com/v1.0";
export const GRAPH_DEFAULT_SCOPE = "https://graph.microsoft.com/.default";

export class GraphApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown, url: string) {
    super(`Graph API request to ${url} failed with status ${status}: ${JSON.stringify(body)}`);
    this.name = "GraphApiError";
    this.status = status;
    this.body = body;
  }
}

export interface GraphRequestOptions {
  query?: Record<string, string | number | undefined>;
  body?: unknown;
  /** Extra scopes for the token request. Defaults to the Graph .default scope. */
  scopes?: string[];
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

  async request<T = unknown>(
    method: "GET" | "POST" | "PATCH" | "DELETE" | "PUT",
    path: string,
    options: GraphRequestOptions = {}
  ): Promise<T> {
    const scopes = options.scopes ?? this.defaultScopes;
    const token = await this.getToken(scopes);
    const url = this.buildUrl(path, options.query);

    const res = await fetch(url, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });

    if (res.status === 204) {
      return undefined as T;
    }

    const text = await res.text();
    const parsed = text ? JSON.parse(text) : undefined;

    if (!res.ok) {
      throw new GraphApiError(res.status, parsed, url);
    }

    return parsed as T;
  }

  get<T = unknown>(path: string, options?: GraphRequestOptions): Promise<T> {
    return this.request<T>("GET", path, options);
  }
  post<T = unknown>(path: string, options?: GraphRequestOptions): Promise<T> {
    return this.request<T>("POST", path, options);
  }
  patch<T = unknown>(path: string, options?: GraphRequestOptions): Promise<T> {
    return this.request<T>("PATCH", path, options);
  }
  put<T = unknown>(path: string, options?: GraphRequestOptions): Promise<T> {
    return this.request<T>("PUT", path, options);
  }
  delete<T = unknown>(path: string, options?: GraphRequestOptions): Promise<T> {
    return this.request<T>("DELETE", path, options);
  }

  /** Follows @odata.nextLink until exhausted or maxPages is reached. */
  async getAllPages<T = unknown>(
    path: string,
    options: GraphRequestOptions & { maxPages?: number } = {}
  ): Promise<T[]> {
    const maxPages = options.maxPages ?? 10;
    const items: T[] = [];
    let next: string | undefined = this.buildUrl(path, options.query);
    let page = 0;

    while (next && page < maxPages) {
      const scopes = options.scopes ?? this.defaultScopes;
      const token = await this.getToken(scopes);
      const res: Response = await fetch(next, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const body = (await res.json()) as { value?: T[]; "@odata.nextLink"?: string };
      if (!res.ok) {
        throw new GraphApiError(res.status, body, next);
      }
      items.push(...(body.value ?? []));
      next = body["@odata.nextLink"];
      page += 1;
    }

    return items;
  }
}
