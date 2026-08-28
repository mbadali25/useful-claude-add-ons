import { test, describe } from "node:test";
import assert from "node:assert/strict";
import type { TokenCredential } from "@azure/identity";
import { runDoctor } from "../src/doctor.js";

function fakeJwt(payload: Record<string, unknown>): string {
  const b64url = (obj: unknown) =>
    Buffer.from(JSON.stringify(obj)).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${b64url({ alg: "none" })}.${b64url(payload)}.signature`;
}

function credentialReturning(token: string | null, expiresOnTimestamp?: number): TokenCredential {
  return {
    getToken: async () => (token === null ? null : { token, expiresOnTimestamp: expiresOnTimestamp ?? 0 }),
  };
}

function credentialThrowing(message: string): TokenCredential {
  return {
    getToken: async () => {
      throw new Error(message);
    },
  };
}

describe("runDoctor", () => {
  test("app-only mode reports the roles claim, not scp", async () => {
    const token = fakeJwt({ roles: ["User.Read.All", "Group.Read.All"], tid: "tenant-1", appid: "app-1" });
    const result = await runDoctor(credentialReturning(token), "app-only");
    assert.equal(result.ok, true);
    assert.equal(result.mode, "app-only");
    assert.equal(result.tenantId, "tenant-1");
    assert.equal(result.identity, "app-1");
    assert.deepEqual(result.scopesOrRoles, ["User.Read.All", "Group.Read.All"]);
  });

  test("delegated mode reports the space-separated scp claim, not roles", async () => {
    const token = fakeJwt({ scp: "Mail.Read Calendars.ReadWrite", upn: "user@contoso.com", tid: "tenant-2" });
    const result = await runDoctor(credentialReturning(token), "delegated");
    assert.equal(result.ok, true);
    assert.equal(result.mode, "delegated");
    assert.equal(result.identity, "user@contoso.com");
    assert.deepEqual(result.scopesOrRoles, ["Mail.Read", "Calendars.ReadWrite"]);
  });

  test("reports writesAllowed from MCP_MS_ALLOW_WRITES", async () => {
    const token = fakeJwt({ roles: [] });
    process.env.MCP_MS_ALLOW_WRITES = "1";
    try {
      const result = await runDoctor(credentialReturning(token), "app-only");
      assert.equal(result.writesAllowed, true);
    } finally {
      delete process.env.MCP_MS_ALLOW_WRITES;
    }
  });

  test("ok:false with no crash when getToken returns null", async () => {
    const result = await runDoctor(credentialReturning(null), "app-only");
    assert.equal(result.ok, false);
    assert.match(result.error ?? "", /getToken returned null/);
  });

  test("ok:false with the error message when getToken throws", async () => {
    const result = await runDoctor(credentialThrowing("AADSTS700016: invalid client"), "app-only");
    assert.equal(result.ok, false);
    assert.match(result.error ?? "", /AADSTS700016/);
  });
});
