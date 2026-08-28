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

describe("mcp-o365-admin tools", () => {
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

  test("list_mailboxes is read-only", async () => {
    globalThis.fetch = (async () =>
      new Response(JSON.stringify({ value: [{ id: "u1", mail: "a@contoso.com" }] }), { status: 200 })) as typeof fetch;

    const tools = buildServer();
    const result: any = await (tools.list_mailboxes.handler as any)({}, {});
    assert.equal(result.isError, undefined);
    assert.match(result.content[0].text, /contoso.com/);
  });

  test("delete_user is blocked without MCP_MS_ALLOW_WRITES", async () => {
    const tools = buildServer();
    const result: any = await (tools.delete_user.handler as any)({ userId: "u1", confirm: true }, {});
    assert.equal(result.isError, true);
    assert.match(result.content[0].text, /blocked/i);
  });

  test("delete_user is blocked without confirm:true even if writes are allowed", async () => {
    process.env.MCP_MS_ALLOW_WRITES = "1";
    const tools = buildServer();
    const result: any = await (tools.delete_user.handler as any)({ userId: "u1" }, {});
    assert.equal(result.isError, true);
  });

  test("delete_user DELETEs the right user when both gates are open", async () => {
    process.env.MCP_MS_ALLOW_WRITES = "1";
    let capturedUrl = "";
    let capturedMethod = "";
    globalThis.fetch = (async (url: string, init?: RequestInit) => {
      capturedUrl = String(url);
      capturedMethod = init?.method ?? "";
      return new Response(null, { status: 204 });
    }) as typeof fetch;

    const tools = buildServer();
    const result: any = await (tools.delete_user.handler as any)({ userId: "u1", confirm: true }, {});

    assert.equal(capturedMethod, "DELETE");
    assert.match(capturedUrl, /\/users\/u1$/);
    assert.equal(result.isError, undefined);
  });

  test("reset_user_password requires the write gate", async () => {
    const tools = buildServer();
    const result: any = await (tools.reset_user_password.handler as any)(
      { userId: "u1", newPassword: "Sup3rSecret!", confirm: true },
      {}
    );
    assert.equal(result.isError, true);
  });

  test("reset_user_password sets forceChangePasswordNextSignIn when both gates are open", async () => {
    process.env.MCP_MS_ALLOW_WRITES = "1";
    let capturedBody: any;
    globalThis.fetch = (async (_url: string, init?: RequestInit) => {
      capturedBody = JSON.parse(String(init?.body));
      return new Response(null, { status: 204 });
    }) as typeof fetch;

    const tools = buildServer();
    await (tools.reset_user_password.handler as any)({ userId: "u1", newPassword: "Sup3rSecret!", confirm: true }, {});

    assert.equal(capturedBody.passwordProfile.forceChangePasswordNextSignIn, true);
    assert.equal(capturedBody.passwordProfile.password, "Sup3rSecret!");
  });

  test("assign_license requires the write gate", async () => {
    const tools = buildServer();
    const result: any = await (tools.assign_license.handler as any)({ userId: "u1", skuId: "sku1", confirm: true }, {});
    assert.equal(result.isError, true);
  });
});
