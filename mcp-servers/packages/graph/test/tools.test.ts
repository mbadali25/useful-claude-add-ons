import { test, describe, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import type { TokenCredential } from "@azure/identity";
import { GraphClient } from "@badali404/mcp-ms-core";
import { createServer } from "../src/index.js";

const fakeCredential: TokenCredential = {
  getToken: async () => ({ token: "fake-token", expiresOnTimestamp: Date.now() + 3600_000 }),
};

function buildServer() {
  const client = new GraphClient(fakeCredential);
  return createServer(client).tools;
}

describe("mcp-msgraph tools", () => {
  const originalFetch = globalThis.fetch;
  const originalWrites = process.env.MCP_MS_ALLOW_WRITES;

  beforeEach(() => {
    delete process.env.MCP_MS_ALLOW_WRITES;
  });
  afterEach(() => {
    globalThis.fetch = originalFetch;
    if (originalWrites === undefined) delete process.env.MCP_MS_ALLOW_WRITES;
    else process.env.MCP_MS_ALLOW_WRITES = originalWrites;
  });

  test("list_users is registered and read-only", async () => {
    globalThis.fetch = (async () =>
      new Response(JSON.stringify({ value: [{ id: "u1", displayName: "Jane" }] }), { status: 200 })) as typeof fetch;

    const tools = buildServer();
    assert.ok(tools.list_users);
    const result: any = await (tools.list_users.handler as any)({}, {});
    assert.equal(result.isError, undefined);
    assert.match(result.content[0].text, /Jane/);
  });

  test("get_user encodes the userId into the path", async () => {
    let capturedUrl = "";
    globalThis.fetch = (async (url: string) => {
      capturedUrl = String(url);
      return new Response(JSON.stringify({ id: "u1" }), { status: 200 });
    }) as typeof fetch;

    const tools = buildServer();
    await (tools.get_user.handler as any)({ userId: "user@contoso.com" }, {});
    assert.ok(capturedUrl.includes("user%40contoso.com"));
  });

  test("update_user_profile is blocked without MCP_MS_ALLOW_WRITES", async () => {
    const tools = buildServer();
    const result: any = await (tools.update_user_profile.handler as any)(
      { userId: "u1", displayName: "New Name", confirm: true },
      {}
    );
    assert.equal(result.isError, true);
    assert.match(result.content[0].text, /blocked/i);
  });

  test("update_user_profile is blocked without confirm:true even if writes are allowed", async () => {
    process.env.MCP_MS_ALLOW_WRITES = "1";
    const tools = buildServer();
    const result: any = await (tools.update_user_profile.handler as any)({ userId: "u1", displayName: "New Name" }, {});
    assert.equal(result.isError, true);
  });

  test("update_user_profile succeeds with both gates open and PATCHes only supplied fields", async () => {
    process.env.MCP_MS_ALLOW_WRITES = "1";
    let capturedMethod = "";
    let capturedBody: any;
    globalThis.fetch = (async (url: string, init?: RequestInit) => {
      capturedMethod = init?.method ?? "";
      capturedBody = JSON.parse(String(init?.body));
      return new Response(null, { status: 204 });
    }) as typeof fetch;

    const tools = buildServer();
    const result: any = await (tools.update_user_profile.handler as any)(
      { userId: "u1", displayName: "New Name", confirm: true },
      {}
    );

    assert.equal(capturedMethod, "PATCH");
    assert.deepEqual(capturedBody, { displayName: "New Name" });
    assert.equal(result.isError, undefined);
  });

  test("remove_group_member is blocked without the write gate", async () => {
    const tools = buildServer();
    const result: any = await (tools.remove_group_member.handler as any)(
      { groupId: "g1", userId: "u1", confirm: true },
      {}
    );
    assert.equal(result.isError, true);
  });
});
