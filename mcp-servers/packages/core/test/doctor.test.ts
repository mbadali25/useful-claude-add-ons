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

const asAppOnly = () => ({ authMode: "secret" as const, tokenType: "app-only" as const });
const asDelegated = () => ({ authMode: "cli" as const, tokenType: "delegated" as const });

describe("runDoctor", () => {
  test("app-only mode reports the roles claim, not scp", async () => {
    const token = fakeJwt({ roles: ["User.Read.All", "Group.Read.All"], tid: "tenant-1", appid: "app-1" });
    const result = await runDoctor(credentialReturning(token), asAppOnly);
    assert.equal(result.ok, true);
    assert.equal(result.authMode, "secret");
    assert.equal(result.tokenType, "app-only");
    assert.equal(result.tenantId, "tenant-1");
    assert.equal(result.identity, "app-1");
    assert.deepEqual(result.scopesOrRoles, ["User.Read.All", "Group.Read.All"]);
  });

  test("delegated mode reports the space-separated scp claim, not roles", async () => {
    const token = fakeJwt({ scp: "Mail.Read Calendars.ReadWrite", upn: "user@contoso.com", tid: "tenant-2" });
    const result = await runDoctor(credentialReturning(token), asDelegated);
    assert.equal(result.ok, true);
    assert.equal(result.authMode, "cli");
    assert.equal(result.tokenType, "delegated");
    assert.equal(result.identity, "user@contoso.com");
    assert.deepEqual(result.scopesOrRoles, ["Mail.Read", "Calendars.ReadWrite"]);
  });

  test("reports which auth mode resolveAuthMode names, even distinct per-call values", async () => {
    const token = fakeJwt({ roles: [] });
    const result = await runDoctor(credentialReturning(token), () => ({ authMode: "device", tokenType: "delegated" }));
    assert.equal(result.authMode, "device");
    assert.equal(result.tokenType, "delegated");
  });

  test("reports writesAllowed from MCP_MS_ALLOW_WRITES", async () => {
    const token = fakeJwt({ roles: [] });
    process.env.MCP_MS_ALLOW_WRITES = "1";
    try {
      const result = await runDoctor(credentialReturning(token), asAppOnly);
      assert.equal(result.writesAllowed, true);
    } finally {
      delete process.env.MCP_MS_ALLOW_WRITES;
    }
  });

  test("ok:false with no crash when getToken returns null", async () => {
    const result = await runDoctor(credentialReturning(null), asAppOnly);
    assert.equal(result.ok, false);
    assert.match(result.error ?? "", /getToken returned null/);
  });

  test("ok:false with the error message when getToken throws, and still reports a mode", async () => {
    const result = await runDoctor(
      credentialThrowing("AADSTS700016: invalid client"),
      () => ({ authMode: "chain exhausted", tokenType: "app-only" })
    );
    assert.equal(result.ok, false);
    assert.match(result.error ?? "", /AADSTS700016/);
    assert.equal(result.authMode, "chain exhausted");
  });
});
