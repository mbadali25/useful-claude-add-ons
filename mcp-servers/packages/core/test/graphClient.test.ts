import { test, describe, afterEach } from "node:test";
import assert from "node:assert/strict";
import type { TokenCredential } from "@azure/identity";
import { GraphClient, GraphApiError, GraphOriginError } from "../src/graphClient.js";

const fakeCredential: TokenCredential = {
  getToken: async () => ({ token: "fake-token", expiresOnTimestamp: Date.now() + 3600_000 }),
};

describe("GraphClient", () => {
  const originalFetch = globalThis.fetch;
  const originalSetTimeout = globalThis.setTimeout;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    globalThis.setTimeout = originalSetTimeout;
  });

  /** Every retry-loop test stubs setTimeout so the 429/backoff tests don't
   * actually wait -- they assert retry behavior, not real elapsed time. Also
   * records every requested wait so a test can assert on it. */
  function stubSleepInstant(): number[] {
    const waits: number[] = [];
    globalThis.setTimeout = ((fn: () => void, ms?: number) => {
      waits.push(ms ?? 0);
      fn();
      return 0 as unknown as ReturnType<typeof setTimeout>;
    }) as typeof setTimeout;
    return waits;
  }

  test("GET sends bearer token and parses JSON body", async () => {
    let capturedUrl = "";
    let capturedAuth = "";
    globalThis.fetch = (async (url: string, init?: RequestInit) => {
      capturedUrl = String(url);
      capturedAuth = (init?.headers as Record<string, string>).Authorization;
      return new Response(JSON.stringify({ id: "abc" }), { status: 200 });
    }) as typeof fetch;

    const client = new GraphClient(fakeCredential);
    const result = await client.get<{ id: string }>("/me");

    assert.equal(result.id, "abc");
    assert.equal(capturedUrl, "https://graph.microsoft.com/v1.0/me");
    assert.equal(capturedAuth, "Bearer fake-token");
  });

  test("GET builds query string, skipping undefined values", async () => {
    let capturedUrl = "";
    globalThis.fetch = (async (url: string) => {
      capturedUrl = String(url);
      return new Response(JSON.stringify({}), { status: 200 });
    }) as typeof fetch;

    const client = new GraphClient(fakeCredential);
    await client.get("/users", { query: { $top: 5, $filter: undefined, $select: "id,displayName" } });

    const url = new URL(capturedUrl);
    assert.equal(url.searchParams.get("$top"), "5");
    assert.equal(url.searchParams.get("$filter"), null);
    assert.equal(url.searchParams.get("$select"), "id,displayName");
  });

  test("non-2xx JSON response throws GraphApiError carrying status and body", async () => {
    globalThis.fetch = (async () =>
      new Response(JSON.stringify({ error: { code: "Forbidden", message: "nope" } }), { status: 403 })) as typeof fetch;

    const client = new GraphClient(fakeCredential);
    await assert.rejects(
      () => client.get("/me"),
      (err: unknown) => {
        assert.ok(err instanceof GraphApiError);
        assert.equal(err.status, 403);
        assert.equal((err.body as any).error.code, "Forbidden");
        return true;
      }
    );
  });

  test("non-JSON error body (e.g. WAF HTML, plain-text 5xx) still surfaces the real status", async () => {
    globalThis.fetch = (async () =>
      new Response("<html><body>Bad Gateway</body></html>", {
        status: 502,
        headers: { "content-type": "text/html" },
      })) as typeof fetch;

    const client = new GraphClient(fakeCredential);
    await assert.rejects(
      () => client.get("/me"),
      (err: unknown) => {
        // Must be the real GraphApiError, not a SyntaxError from JSON.parse --
        // that was the bug: parsing before checking res.ok threw and lost the
        // 502 inside a confusing "Unexpected token '<'" instead.
        assert.ok(err instanceof GraphApiError);
        assert.equal(err.status, 502);
        assert.match(String(err.body), /Bad Gateway/);
        return true;
      }
    );
  });

  test("204 No Content resolves to undefined", async () => {
    globalThis.fetch = (async () => new Response(null, { status: 204 })) as typeof fetch;
    const client = new GraphClient(fakeCredential);
    const result = await client.delete("/me/messages/1");
    assert.equal(result, undefined);
  });

  test("empty 200 body (no content-length) resolves to undefined, not a parse error", async () => {
    globalThis.fetch = (async () => new Response("", { status: 200 })) as typeof fetch;
    const client = new GraphClient(fakeCredential);
    const result = await client.post("/me/sendMail");
    assert.equal(result, undefined);
  });

  test("429 with Retry-After (seconds) retries and eventually succeeds", async () => {
    const waits = stubSleepInstant();
    let call = 0;
    globalThis.fetch = (async () => {
      call += 1;
      if (call === 1) {
        return new Response("throttled", { status: 429, headers: { "Retry-After": "1" } });
      }
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }) as typeof fetch;

    const client = new GraphClient(fakeCredential);
    const result = await client.get<{ ok: boolean }>("/me");

    assert.equal(call, 2);
    assert.equal(result.ok, true);
    assert.deepEqual(waits, [1000]);
  });

  test("429 retry is bounded -- gives up after the retry budget and surfaces a real GraphApiError", async () => {
    stubSleepInstant();
    let call = 0;
    globalThis.fetch = (async () => {
      call += 1;
      return new Response("still throttled", { status: 429, headers: { "Retry-After": "0" } });
    }) as typeof fetch;

    const client = new GraphClient(fakeCredential);
    await assert.rejects(
      () => client.get("/me"),
      (err: unknown) => {
        assert.ok(err instanceof GraphApiError);
        assert.equal(err.status, 429);
        return true;
      }
    );
    // 1 initial attempt + 3 retries = 4 fetches, never an unbounded loop.
    assert.equal(call, 4);
  });

  test("429 retry wait is capped even when Retry-After asks for longer", async () => {
    const waits = stubSleepInstant();
    let call = 0;
    globalThis.fetch = (async () => {
      call += 1;
      if (call === 1) {
        return new Response("throttled", { status: 429, headers: { "Retry-After": "9999" } });
      }
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }) as typeof fetch;

    const client = new GraphClient(fakeCredential);
    await client.get("/me");
    assert.equal(waits.length, 1);
    assert.ok(waits[0] <= 30_000, `expected wait capped at 30s, got ${waits[0]}ms`);
  });

  test("getAllPages follows @odata.nextLink until exhausted and reports truncated:false", async () => {
    const pages = [
      { value: [{ id: 1 }, { id: 2 }], "@odata.nextLink": "https://graph.microsoft.com/v1.0/users?page=2" },
      { value: [{ id: 3 }] },
    ];
    let call = 0;
    globalThis.fetch = (async () => {
      const body = pages[call];
      call += 1;
      return new Response(JSON.stringify(body), { status: 200 });
    }) as typeof fetch;

    const client = new GraphClient(fakeCredential);
    const page = await client.getAllPages<{ id: number }>("/users");

    assert.equal(page.items.length, 3);
    assert.equal(page.truncated, false);
    assert.equal(call, 2);
  });

  test("getAllPages stops at maxPages and reports truncated:true", async () => {
    globalThis.fetch = (async () =>
      new Response(
        JSON.stringify({ value: [{ id: 1 }], "@odata.nextLink": "https://graph.microsoft.com/v1.0/users?page=next" }),
        { status: 200 }
      )) as typeof fetch;

    const client = new GraphClient(fakeCredential);
    const page = await client.getAllPages("/users", { maxPages: 2 });
    assert.equal(page.items.length, 2); // 1 item per page, 2 pages
    assert.equal(page.truncated, true);
  });

  test("getAllPages reports truncated:false when the last page has no nextLink", async () => {
    globalThis.fetch = (async () => new Response(JSON.stringify({ value: [{ id: 1 }] }), { status: 200 })) as typeof fetch;

    const client = new GraphClient(fakeCredential);
    const page = await client.getAllPages("/users", { maxPages: 5 });
    assert.equal(page.truncated, false);
  });

  test("getAllPages surfaces a non-JSON error body as a real GraphApiError", async () => {
    globalThis.fetch = (async () => new Response("service unavailable", { status: 503 })) as typeof fetch;

    const client = new GraphClient(fakeCredential);
    await assert.rejects(
      () => client.getAllPages("/users"),
      (err: unknown) => {
        assert.ok(err instanceof GraphApiError);
        assert.equal(err.status, 503);
        assert.match(String(err.body), /service unavailable/);
        return true;
      }
    );
  });

  // --- T-0090: the Bearer token goes only to the configured Graph origin ------
  //
  // Must-block cases assert three things: the call is refused with a
  // GraphOriginError, nothing is fetched beyond the pages already on the Graph
  // origin, and no token is acquired for the refused URL. On the unpinned
  // client each one fails with the foreign URL listed as having received
  // "Bearer fake-token" -- that output is the leak, reproduced.

  const GRAPH_ORIGIN = "https://graph.microsoft.com";

  interface FetchCall {
    url: string;
    auth: string | undefined;
  }

  function countingCredential(): { credential: TokenCredential; calls: () => number } {
    let n = 0;
    return {
      credential: {
        getToken: async () => {
          n += 1;
          return { token: "fake-token", expiresOnTimestamp: Date.now() + 3600_000 };
        },
      },
      calls: () => n,
    };
  }

  /** Records every fetch and answers each with the next canned JSON body, then
   * `{}` once they run out -- so on an unpinned client a foreign fetch resolves
   * and the test fails on the missing refusal, not on a stub crash. */
  function recordFetch(responses: unknown[] = []): FetchCall[] {
    const calls: FetchCall[] = [];
    globalThis.fetch = (async (url: string | URL, init?: RequestInit) => {
      const headers = (init?.headers ?? {}) as Record<string, string>;
      calls.push({ url: String(url), auth: headers.Authorization });
      const body = calls.length <= responses.length ? responses[calls.length - 1] : {};
      return new Response(JSON.stringify(body), { status: 200 });
    }) as typeof fetch;
    return calls;
  }

  function assertRefused(err: unknown, refusedOrigin: string, expectedOrigin: string = GRAPH_ORIGIN): void {
    const e = err as { name?: unknown; message?: unknown };
    assert.equal(e.name, "GraphOriginError", `expected a GraphOriginError, got ${String(err)}`);
    const message = String(e.message);
    assert.ok(message.includes(refusedOrigin), `message should name the refused origin ${refusedOrigin}: ${message}`);
    assert.ok(
      message.includes(`Only ${expectedOrigin} is allowed`),
      `message should name the expected origin ${expectedOrigin}: ${message}`
    );
    assert.ok(!message.includes("fake-token"), `message must never carry the token: ${message}`);
  }

  /** Runs `call` and requires a GraphOriginError. When the client resolves
   * instead, fails with every URL it fetched and the Authorization each one
   * carried -- the evidence of the leak on the unpinned client. */
  async function expectRefused(
    call: () => Promise<unknown>,
    fetched: FetchCall[],
    refusedOrigin: string,
    expectedOrigin: string = GRAPH_ORIGIN
  ): Promise<Error> {
    let caught: unknown;
    try {
      await call();
    } catch (err) {
      caught = err;
    }
    if (caught === undefined) {
      assert.fail(
        `expected a GraphOriginError, but the client resolved after fetching: ` +
          fetched.map((c) => `${c.url} (Authorization: ${c.auth})`).join(", ")
      );
    }
    assertRefused(caught, refusedOrigin, expectedOrigin);
    return caught as Error;
  }

  const getBlocked: Array<{ name: string; url: string; refused: string; base?: string; match?: RegExp }> = [
    { name: "get refuses an absolute URL on a foreign host", url: "https://evil.example/v1.0/me", refused: "https://evil.example" },
    {
      name: "get refuses a look-alike host",
      url: "https://graph.microsoft.com.evil.example/v1.0/me",
      refused: "https://graph.microsoft.com.evil.example",
    },
    {
      name: "get refuses a userinfo URL",
      url: "https://graph.microsoft.com@evil.example/v1.0/me",
      refused: "https://evil.example",
    },
    {
      name: "get refuses userinfo on the Graph host",
      url: "https://user:pw@graph.microsoft.com/v1.0/me",
      refused: "https://graph.microsoft.com",
      match: /username or password/,
    },
    { name: "get refuses an http downgrade", url: "http://graph.microsoft.com/v1.0/me", refused: "http://graph.microsoft.com" },
    {
      name: "get refuses a port change",
      url: "https://graph.microsoft.com:8443/v1.0/me",
      refused: "https://graph.microsoft.com:8443",
    },
    {
      name: "get refuses a path that concatenates off a path-less base",
      url: ".evil.example/x",
      base: "https://graph.microsoft.com",
      refused: "https://graph.microsoft.com.evil.example",
    },
  ];

  for (const c of getBlocked) {
    test(c.name, async () => {
      const cred = countingCredential();
      const fetched = recordFetch([{ id: "leaked" }]);
      const client = new GraphClient(cred.credential, c.base);

      const err = await expectRefused(() => client.get(c.url), fetched, c.refused);

      if (c.match) assert.match(err.message, c.match);
      assert.equal(fetched.length, 0, "a refused URL must never be fetched");
      assert.equal(cred.calls(), 0, "a refused URL must cost no token acquisition");
    });
  }

  const nextLinkBlocked: Array<{ name: string; nextLink: string; refused: string; secret?: string }> = [
    {
      name: "getAllPages refuses a nextLink on a foreign host",
      nextLink: "https://evil.example/v1.0/users?$skiptoken=SECRETPAGE",
      refused: "https://evil.example",
      secret: "SECRETPAGE",
    },
    {
      name: "getAllPages refuses a look-alike nextLink",
      nextLink: "https://graph.microsoft.com.evil.example/v1.0/users?page=2",
      refused: "https://graph.microsoft.com.evil.example",
    },
    {
      name: "getAllPages refuses a userinfo nextLink",
      nextLink: "https://graph.microsoft.com@evil.example/v1.0/users",
      refused: "https://evil.example",
    },
    {
      name: "getAllPages refuses an http nextLink",
      nextLink: "http://graph.microsoft.com/v1.0/users?page=2",
      refused: "http://graph.microsoft.com",
    },
    {
      name: "getAllPages refuses a nextLink with another port",
      nextLink: "https://graph.microsoft.com:8443/v1.0/users?page=2",
      refused: "https://graph.microsoft.com:8443",
    },
    {
      name: "getAllPages refuses a non-absolute nextLink",
      nextLink: "//evil.example/v1.0/users",
      refused: "<not an absolute URL>",
    },
  ];

  for (const c of nextLinkBlocked) {
    test(c.name, async () => {
      const cred = countingCredential();
      const fetched = recordFetch([{ value: [{ id: 1 }], "@odata.nextLink": c.nextLink }, { value: [{ id: 2 }] }]);
      const client = new GraphClient(cred.credential);

      const err = await expectRefused(() => client.getAllPages("/users"), fetched, c.refused);

      if (c.secret) assert.ok(!err.message.includes(c.secret), `message must not carry the query: ${err.message}`);
      assert.deepEqual(
        fetched.map((f) => f.url),
        ["https://graph.microsoft.com/v1.0/users"],
        "only page 1, on the Graph origin, may be fetched"
      );
      assert.equal(cred.calls(), 1, "no token may be acquired for the refused nextLink");
    });
  }

  test("getAllPages follows a graph.microsoft.com nextLink", async () => {
    const nextLink = "https://graph.microsoft.com/v1.0/users?$skiptoken=abc";
    const fetched = recordFetch([{ value: [{ id: 1 }], "@odata.nextLink": nextLink }, { value: [{ id: 2 }] }]);
    const client = new GraphClient(fakeCredential);

    const page = await client.getAllPages<{ id: number }>("/users");

    assert.deepEqual(page.items, [{ id: 1 }, { id: 2 }]);
    assert.deepEqual(fetched, [
      { url: "https://graph.microsoft.com/v1.0/users", auth: "Bearer fake-token" },
      { url: nextLink, auth: "Bearer fake-token" },
    ]);
  });

  test("getAllPages follows a nextLink with explicit :443 and upper-case host", async () => {
    const fetched = recordFetch([
      { value: [{ id: 1 }], "@odata.nextLink": "https://GRAPH.microsoft.com:443/beta/users?page=2" },
      { value: [{ id: 2 }] },
    ]);
    const client = new GraphClient(fakeCredential);

    const page = await client.getAllPages<{ id: number }>("/users");

    assert.equal(fetched.length, 2);
    assert.equal(page.items.length, 2);
  });

  test("get accepts an absolute URL on the base origin", async () => {
    const fetched = recordFetch([{ id: "me" }]);
    const client = new GraphClient(fakeCredential);

    const result = await client.get<{ id: string }>("https://graph.microsoft.com/beta/me");

    assert.equal(result.id, "me");
    assert.deepEqual(fetched, [{ url: "https://graph.microsoft.com/beta/me", auth: "Bearer fake-token" }]);
  });

  test("a custom base pins to its own origin", async () => {
    const base = "https://graph.microsoft.us/v1.0";
    const client = new GraphClient(fakeCredential, base);

    recordFetch([{ value: [{ id: 1 }], "@odata.nextLink": "https://graph.microsoft.us/v1.0/users?page=2" }, { value: [{ id: 2 }] }]);
    const page = await client.getAllPages<{ id: number }>("/users");
    assert.equal(page.items.length, 2);

    const fetched = recordFetch([{ value: [{ id: 1 }], "@odata.nextLink": "https://graph.microsoft.com/v1.0/users?page=2" }]);
    await expectRefused(() => client.getAllPages("/users"), fetched, "https://graph.microsoft.com", "https://graph.microsoft.us");
    assert.equal(fetched.length, 1);
  });

  test("refusal message names both origins and never the token or query", async () => {
    const fetched = recordFetch([
      { value: [{ id: 1 }], "@odata.nextLink": "https://evil.example/v1.0/users?$skiptoken=SECRETPAGE&x=1" },
    ]);
    const client = new GraphClient(fakeCredential);

    const err = await expectRefused(() => client.getAllPages("/users"), fetched, "https://evil.example");

    assert.ok(err instanceof GraphOriginError);
    assert.equal(err.refusedOrigin, "https://evil.example");
    assert.equal(err.expectedOrigin, GRAPH_ORIGIN);
    assert.ok(err.message.includes("https://evil.example"));
    assert.ok(err.message.includes(GRAPH_ORIGIN));
    assert.ok(!err.message.includes("fake-token"));
    assert.ok(!err.message.includes("SECRETPAGE"));
    assert.ok(!err.message.includes("?"));
  });
});
