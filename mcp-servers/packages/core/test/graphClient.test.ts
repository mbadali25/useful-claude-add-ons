import { test, describe, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import type { TokenCredential } from "@azure/identity";
import { GraphClient, GraphApiError } from "../src/graphClient.js";

const fakeCredential: TokenCredential = {
  getToken: async () => ({ token: "fake-token", expiresOnTimestamp: Date.now() + 3600_000 }),
};

describe("GraphClient", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

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

  test("non-2xx response throws GraphApiError carrying status and body", async () => {
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

  test("204 No Content resolves to undefined", async () => {
    globalThis.fetch = (async () => new Response(null, { status: 204 })) as typeof fetch;
    const client = new GraphClient(fakeCredential);
    const result = await client.delete("/me/messages/1");
    assert.equal(result, undefined);
  });

  test("getAllPages follows @odata.nextLink until exhausted", async () => {
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
    const items = await client.getAllPages<{ id: number }>("/users");

    assert.equal(items.length, 3);
    assert.equal(call, 2);
  });

  test("getAllPages stops at maxPages even if nextLink remains", async () => {
    globalThis.fetch = (async () =>
      new Response(
        JSON.stringify({ value: [{ id: 1 }], "@odata.nextLink": "https://graph.microsoft.com/v1.0/users?page=next" }),
        { status: 200 }
      )) as typeof fetch;

    const client = new GraphClient(fakeCredential);
    const items = await client.getAllPages("/users", { maxPages: 2 });
    assert.equal(items.length, 2); // 1 item per page, 2 pages
  });
});
