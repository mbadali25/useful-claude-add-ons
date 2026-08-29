import { test, describe, afterEach } from "node:test";
import assert from "node:assert/strict";
import type { TokenCredential } from "@azure/identity";
import { GraphClient, GraphApiError } from "../src/graphClient.js";

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
});
