import { test, describe, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import type { TokenCredential } from "@azure/identity";
import { AdminCredentialChain, buildAdminCredential, type ChainLink } from "../src/adminAuth.js";
import { ConfigError, logToStderr } from "../src/auth.js";
import { runDoctor } from "../src/doctor.js";

function fakeJwt(payload: Record<string, unknown>): string {
  const b64url = (obj: unknown) =>
    Buffer.from(JSON.stringify(obj)).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${b64url({ alg: "none" })}.${b64url(payload)}.signature`;
}

function fakeCredential(behavior: { token?: string; throwMessage?: string; capturedScopes?: string[] }): TokenCredential {
  return {
    getToken: async (scopes: string | string[]) => {
      if (behavior.capturedScopes) behavior.capturedScopes.push(...(Array.isArray(scopes) ? scopes : [scopes]));
      if (behavior.throwMessage) throw new Error(behavior.throwMessage);
      return { token: behavior.token ?? "fake-token", expiresOnTimestamp: Date.now() + 3600_000 };
    },
  };
}

function link(
  mode: ChainLink["mode"],
  opts: { throwMessage?: string; token?: string; scopesOverride?: string[]; capturedScopes?: string[] } = {}
): { link: ChainLink; buildCount: () => number } {
  let count = 0;
  const l: ChainLink = {
    mode,
    tokenType: mode === "secret" ? "app-only" : "delegated",
    scopesOverride: opts.scopesOverride,
    build: () => {
      count += 1;
      return fakeCredential({ token: opts.token, throwMessage: opts.throwMessage, capturedScopes: opts.capturedScopes });
    },
  };
  return { link: l, buildCount: () => count };
}

describe("AdminCredentialChain", () => {
  test("constructing with zero links throws immediately, no network attempted", () => {
    assert.throws(() => new AdminCredentialChain([]), ConfigError);
  });

  test("secret wins when it succeeds -- cli and device are never built", async () => {
    const secret = link("secret", { token: "secret-token" });
    const cli = link("cli", { token: "cli-token" });
    const device = link("device", { token: "device-token" });
    const chain = new AdminCredentialChain([secret.link, cli.link, device.link]);

    const token = await chain.getToken(["https://graph.microsoft.com/.default"]);

    assert.equal(token?.token, "secret-token");
    assert.equal(chain.usedMode, "secret");
    assert.equal(chain.usedTokenType, "app-only");
    assert.equal(secret.buildCount(), 1);
    assert.equal(cli.buildCount(), 0);
    assert.equal(device.buildCount(), 0);
  });

  test("cli is used when secret is absent from the chain", async () => {
    const cli = link("cli", { token: "cli-token" });
    const device = link("device", { token: "device-token" });
    const chain = new AdminCredentialChain([cli.link, device.link]);

    await chain.getToken(["s"]);

    assert.equal(chain.usedMode, "cli");
    assert.equal(chain.usedTokenType, "delegated");
    assert.equal(device.buildCount(), 0);
  });

  test("device code is the last resort -- only reached when secret and cli both fail", async () => {
    const secret = link("secret", { throwMessage: "no client secret configured" });
    const cli = link("cli", { throwMessage: "az: command not found" });
    const device = link("device", { token: "device-token" });
    const chain = new AdminCredentialChain([secret.link, cli.link, device.link]);

    const token = await chain.getToken(["s"]);

    assert.equal(token?.token, "device-token");
    assert.equal(chain.usedMode, "device");
    assert.equal(secret.buildCount(), 1);
    assert.equal(cli.buildCount(), 1);
    assert.equal(device.buildCount(), 1);
  });

  test("all links failing throws a ConfigError naming every mode tried", async () => {
    const secret = link("secret", { throwMessage: "bad secret" });
    const cli = link("cli", { throwMessage: "az not logged in" });
    const device = link("device", { throwMessage: "device code declined" });
    const chain = new AdminCredentialChain([secret.link, cli.link, device.link]);

    await assert.rejects(
      () => chain.getToken(["s"]),
      (err: unknown) => {
        assert.ok(err instanceof ConfigError);
        assert.match(err.message, /secret/);
        assert.match(err.message, /cli/);
        assert.match(err.message, /device/);
        assert.match(err.message, /bad secret/);
        assert.match(err.message, /az not logged in/);
        assert.match(err.message, /device code declined/);
        return true;
      }
    );
  });

  test("once resolved, the same link's credential is reused -- earlier links are not retried", async () => {
    const secret = link("secret", { throwMessage: "no secret" });
    const cli = link("cli", { token: "cli-token" });
    const chain = new AdminCredentialChain([secret.link, cli.link]);

    await chain.getToken(["s"]);
    await chain.getToken(["s"]);
    await chain.getToken(["s"]);

    assert.equal(secret.buildCount(), 1); // only attempted once, during the first (failed) pass
    assert.equal(cli.buildCount(), 1); // built once, then reused for the 2nd and 3rd calls
  });

  test("secret and cli links ignore caller scopes and always request their override", async () => {
    const captured: string[] = [];
    const secret = link("secret", { scopesOverride: ["https://graph.microsoft.com/.default"], capturedScopes: captured });
    const chain = new AdminCredentialChain([secret.link]);

    await chain.getToken(["https://graph.microsoft.com/DeviceManagementManagedDevices.Read.All"]);

    assert.deepEqual(captured, ["https://graph.microsoft.com/.default"]);
  });

  test("device link has no override -- it requests exactly the caller-supplied delegated scopes", async () => {
    const captured: string[] = [];
    const device = link("device", { capturedScopes: captured });
    const chain = new AdminCredentialChain([device.link]);

    await chain.getToken(["https://graph.microsoft.com/DeviceManagementManagedDevices.Read.All"]);

    assert.deepEqual(captured, ["https://graph.microsoft.com/DeviceManagementManagedDevices.Read.All"]);
  });
});

describe("buildAdminCredential -- MS_ADMIN_AUTH mode selection (env-only, never calls getToken)", () => {
  const envKeys = ["MS_ADMIN_AUTH", "MS_ADMIN_TENANT_ID", "MS_ADMIN_CLIENT_ID", "MS_ADMIN_CLIENT_SECRET"];
  const saved: Record<string, string | undefined> = {};

  beforeEach(() => {
    for (const k of envKeys) {
      saved[k] = process.env[k];
      delete process.env[k];
    }
  });
  afterEach(() => {
    for (const k of envKeys) {
      if (saved[k] === undefined) delete process.env[k];
      else process.env[k] = saved[k];
    }
  });

  test("auto with all three secret vars set: secret, cli, device in that order", () => {
    process.env.MS_ADMIN_TENANT_ID = "t";
    process.env.MS_ADMIN_CLIENT_ID = "c";
    process.env.MS_ADMIN_CLIENT_SECRET = "s";
    const chain = buildAdminCredential(["scope"]);
    assert.deepEqual(chain.configuredModes, ["secret", "cli", "device"]);
  });

  test("auto with secret vars absent: cli then device, no secret link at all", () => {
    const chain = buildAdminCredential(["scope"]);
    assert.deepEqual(chain.configuredModes, ["cli", "device"]);
  });

  test("MS_ADMIN_AUTH=secret with vars set forces exactly that one link", () => {
    process.env.MS_ADMIN_AUTH = "secret";
    process.env.MS_ADMIN_TENANT_ID = "t";
    process.env.MS_ADMIN_CLIENT_ID = "c";
    process.env.MS_ADMIN_CLIENT_SECRET = "s";
    const chain = buildAdminCredential(["scope"]);
    assert.deepEqual(chain.configuredModes, ["secret"]);
  });

  test("MS_ADMIN_AUTH=secret without the three vars throws before any network call", () => {
    process.env.MS_ADMIN_AUTH = "secret";
    assert.throws(() => buildAdminCredential(["scope"]), ConfigError);
  });

  test("MS_ADMIN_AUTH=cli forces exactly that one link, even with secret vars present", () => {
    process.env.MS_ADMIN_AUTH = "cli";
    process.env.MS_ADMIN_TENANT_ID = "t";
    process.env.MS_ADMIN_CLIENT_ID = "c";
    process.env.MS_ADMIN_CLIENT_SECRET = "s";
    const chain = buildAdminCredential(["scope"]);
    assert.deepEqual(chain.configuredModes, ["cli"]);
  });

  test("MS_ADMIN_AUTH=device forces exactly that one link", () => {
    process.env.MS_ADMIN_AUTH = "device";
    const chain = buildAdminCredential(["scope"]);
    assert.deepEqual(chain.configuredModes, ["device"]);
  });

  test("an invalid MS_ADMIN_AUTH value throws a clear ConfigError", () => {
    process.env.MS_ADMIN_AUTH = "bogus";
    assert.throws(() => buildAdminCredential(["scope"]), (err: unknown) => {
      assert.ok(err instanceof ConfigError);
      assert.match(err.message, /bogus/);
      assert.match(err.message, /secret, cli, device, auto/);
      return true;
    });
  });
});

describe("device-code prompt goes to stderr, never stdout", () => {
  test("logToStderr -- the exact function buildDeviceCodeCredential's userPromptCallback delegates to -- never writes stdout", () => {
    const originalStdoutWrite = process.stdout.write;
    const originalStderrWrite = process.stderr.write;
    const stdoutChunks: string[] = [];
    const stderrChunks: string[] = [];
    process.stdout.write = ((chunk: unknown) => {
      stdoutChunks.push(String(chunk));
      return true;
    }) as typeof process.stdout.write;
    process.stderr.write = ((chunk: unknown) => {
      stderrChunks.push(String(chunk));
      return true;
    }) as typeof process.stderr.write;

    try {
      logToStderr("To sign in, use a web browser to open https://microsoft.com/devicelogin and enter the code ABC-123");
    } finally {
      process.stdout.write = originalStdoutWrite;
      process.stderr.write = originalStderrWrite;
    }

    assert.equal(stdoutChunks.length, 0, "stdout is the MCP JSON-RPC channel -- a stray line corrupts framing");
    assert.equal(stderrChunks.length, 1);
    assert.match(stderrChunks[0], /devicelogin/);
  });
});

describe("doctor reports which chain link authenticated", () => {
  test("reports mode:cli, tokenType:delegated when the cli link is the one that resolved", async () => {
    const cli = link("cli", { token: fakeJwt({ scp: "User.Read.All" }) });
    const device = link("device", { token: fakeJwt({ scp: "DeviceManagementManagedDevices.Read.All" }) });
    const chain = new AdminCredentialChain([cli.link, device.link]);

    const result = await runDoctor(
      chain,
      () => ({ authMode: chain.usedMode ?? "none (all methods failed)", tokenType: chain.usedTokenType ?? "app-only" }),
      ["scope"]
    );

    assert.equal(result.ok, true);
    assert.equal(result.authMode, "cli");
    assert.equal(result.tokenType, "delegated");
  });

  test("reports mode:secret, tokenType:app-only when the secret link resolves", async () => {
    const secret = link("secret", { token: fakeJwt({ roles: ["User.Read.All"] }) });
    const chain = new AdminCredentialChain([secret.link]);

    const result = await runDoctor(
      chain,
      () => ({ authMode: chain.usedMode ?? "none (all methods failed)", tokenType: chain.usedTokenType ?? "app-only" }),
      ["scope"]
    );

    assert.equal(result.authMode, "secret");
    assert.equal(result.tokenType, "app-only");
  });

  test("reports a descriptive failure mode when every link in the chain fails", async () => {
    const secret = link("secret", { throwMessage: "bad secret" });
    const device = link("device", { throwMessage: "declined" });
    const chain = new AdminCredentialChain([secret.link, device.link]);

    const result = await runDoctor(
      chain,
      () => ({ authMode: chain.usedMode ?? "none (all methods failed)", tokenType: chain.usedTokenType ?? "app-only" }),
      ["scope"]
    );

    assert.equal(result.ok, false);
    assert.equal(result.authMode, "none (all methods failed)");
    assert.match(result.error ?? "", /bad secret/);
    assert.match(result.error ?? "", /declined/);
  });
});
