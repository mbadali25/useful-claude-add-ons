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

describe("mcp-o365-user tools", () => {
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

  test("get_my_profile calls /me and never any other user's path", async () => {
    let capturedUrl = "";
    globalThis.fetch = (async (url: string) => {
      capturedUrl = String(url);
      return new Response(JSON.stringify({ id: "self", mail: "me@contoso.com" }), { status: 200 });
    }) as typeof fetch;

    const tools = buildServer();
    const result: any = await (tools.get_my_profile.handler as any)({}, {});
    assert.equal(capturedUrl, "https://graph.microsoft.com/v1.0/me");
    assert.match(result.content[0].text, /me@contoso.com/);
  });

  test("list_my_mail defaults to the inbox folder", async () => {
    let capturedUrl = "";
    globalThis.fetch = (async (url: string) => {
      capturedUrl = String(url);
      return new Response(JSON.stringify({ value: [] }), { status: 200 });
    }) as typeof fetch;

    const tools = buildServer();
    await (tools.list_my_mail.handler as any)({}, {});
    assert.match(capturedUrl, /\/me\/mailFolders\/inbox\/messages/);
  });

  test("send_mail is blocked without MCP_MS_ALLOW_WRITES", async () => {
    const tools = buildServer();
    const result: any = await (tools.send_mail.handler as any)(
      { to: ["a@contoso.com"], subject: "hi", body: "hello", confirm: true },
      {}
    );
    assert.equal(result.isError, true);
    assert.match(result.content[0].text, /blocked/i);
  });

  test("send_mail is blocked without confirm:true even if writes are allowed", async () => {
    process.env.MCP_MS_ALLOW_WRITES = "1";
    const tools = buildServer();
    const result: any = await (tools.send_mail.handler as any)(
      { to: ["a@contoso.com"], subject: "hi", body: "hello" },
      {}
    );
    assert.equal(result.isError, true);
  });

  test("send_mail posts to /me/sendMail with both gates open", async () => {
    process.env.MCP_MS_ALLOW_WRITES = "1";
    let capturedUrl = "";
    let capturedBody: any;
    globalThis.fetch = (async (url: string, init?: RequestInit) => {
      capturedUrl = String(url);
      capturedBody = JSON.parse(String(init?.body));
      return new Response(null, { status: 202 });
    }) as typeof fetch;

    const tools = buildServer();
    const result: any = await (tools.send_mail.handler as any)(
      { to: ["a@contoso.com"], subject: "hi", body: "hello", confirm: true },
      {}
    );

    assert.match(capturedUrl, /\/me\/sendMail/);
    assert.equal(capturedBody.message.subject, "hi");
    assert.equal(result.isError, undefined);
  });

  test("delete_mail_message requires the write gate", async () => {
    const tools = buildServer();
    const result: any = await (tools.delete_mail_message.handler as any)({ messageId: "m1", confirm: true }, {});
    assert.equal(result.isError, true);
  });
});
