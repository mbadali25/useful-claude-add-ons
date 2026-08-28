import { test, describe, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import type { TokenCredential } from "@azure/identity";
import { GraphClient } from "@mbadali/mcp-ms-core";
import { createServer } from "../src/index.js";

const fakeCredential: TokenCredential = {
  getToken: async () => ({ token: "fake-token", expiresOnTimestamp: Date.now() + 3600_000 }),
};

function buildServer() {
  const client = new GraphClient(fakeCredential);
  return createServer(client).tools;
}

describe("mcp-intune tools", () => {
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

  test("list_managed_devices is read-only and works with no gate set", async () => {
    globalThis.fetch = (async () =>
      new Response(JSON.stringify({ value: [{ id: "d1", deviceName: "LAPTOP-1" }] }), { status: 200 })) as typeof fetch;

    const tools = buildServer();
    const result: any = await (tools.list_managed_devices.handler as any)({}, {});
    assert.equal(result.isError, undefined);
    assert.match(result.content[0].text, /LAPTOP-1/);
  });

  test("wipe_device is blocked without MCP_MS_ALLOW_WRITES", async () => {
    const tools = buildServer();
    const result: any = await (tools.wipe_device.handler as any)({ deviceId: "d1", confirm: true }, {});
    assert.equal(result.isError, true);
    assert.match(result.content[0].text, /blocked/i);
  });

  test("wipe_device is blocked without confirm:true even if writes are allowed", async () => {
    process.env.MCP_MS_ALLOW_WRITES = "1";
    const tools = buildServer();
    const result: any = await (tools.wipe_device.handler as any)({ deviceId: "d1" }, {});
    assert.equal(result.isError, true);
  });

  test("wipe_device posts to the wipe endpoint when both gates are open", async () => {
    process.env.MCP_MS_ALLOW_WRITES = "1";
    let capturedUrl = "";
    let capturedMethod = "";
    globalThis.fetch = (async (url: string, init?: RequestInit) => {
      capturedUrl = String(url);
      capturedMethod = init?.method ?? "";
      return new Response(null, { status: 204 });
    }) as typeof fetch;

    const tools = buildServer();
    const result: any = await (tools.wipe_device.handler as any)({ deviceId: "d1", confirm: true }, {});

    assert.equal(capturedMethod, "POST");
    assert.match(capturedUrl, /managedDevices\/d1\/wipe/);
    assert.equal(result.isError, undefined);
  });

  test("retire_device and sync_device both require the write gate", async () => {
    const tools = buildServer();
    const retire: any = await (tools.retire_device.handler as any)({ deviceId: "d1", confirm: true }, {});
    const sync: any = await (tools.sync_device.handler as any)({ deviceId: "d1", confirm: true }, {});
    assert.equal(retire.isError, true);
    assert.equal(sync.isError, true);
  });

  test("update_compliance_policy PATCHes only the supplied fields", async () => {
    process.env.MCP_MS_ALLOW_WRITES = "1";
    let capturedBody: any;
    globalThis.fetch = (async (_url: string, init?: RequestInit) => {
      capturedBody = JSON.parse(String(init?.body));
      return new Response(null, { status: 204 });
    }) as typeof fetch;

    const tools = buildServer();
    await (tools.update_compliance_policy.handler as any)(
      { policyId: "p1", patch: { passwordRequired: true }, confirm: true },
      {}
    );
    assert.deepEqual(capturedBody, { passwordRequired: true });
  });
});
