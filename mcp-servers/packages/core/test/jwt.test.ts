import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { decodeJwtPayload } from "../src/jwt.js";

function fakeJwt(payload: Record<string, unknown>): string {
  const b64url = (obj: unknown) =>
    Buffer.from(JSON.stringify(obj)).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${b64url({ alg: "none" })}.${b64url(payload)}.signature`;
}

describe("decodeJwtPayload", () => {
  test("decodes app-only token roles claim", () => {
    const token = fakeJwt({ roles: ["DeviceManagementManagedDevices.Read.All"], tid: "tenant-1" });
    const claims = decodeJwtPayload(token);
    assert.deepEqual(claims.roles, ["DeviceManagementManagedDevices.Read.All"]);
    assert.equal(claims.tid, "tenant-1");
  });

  test("decodes delegated token scp claim", () => {
    const token = fakeJwt({ scp: "Mail.Read Calendars.ReadWrite", upn: "user@contoso.com" });
    const claims = decodeJwtPayload(token);
    assert.equal(claims.scp, "Mail.Read Calendars.ReadWrite");
  });

  test("handles base64url padding correctly (empty edge)", () => {
    const token = fakeJwt({});
    const claims = decodeJwtPayload(token);
    assert.deepEqual(claims, {});
  });

  test("throws on malformed token", () => {
    assert.throws(() => decodeJwtPayload("not-a-jwt"));
  });
});
