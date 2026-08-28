import { test, describe, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { assertWriteAllowed, WriteNotAllowedError } from "../src/writeGate.js";

describe("assertWriteAllowed", () => {
  const original = process.env.MCP_MS_ALLOW_WRITES;

  beforeEach(() => {
    delete process.env.MCP_MS_ALLOW_WRITES;
  });
  afterEach(() => {
    if (original === undefined) delete process.env.MCP_MS_ALLOW_WRITES;
    else process.env.MCP_MS_ALLOW_WRITES = original;
  });

  test("blocks when env flag is unset, even with confirm:true", () => {
    assert.throws(
      () => assertWriteAllowed("delete_user", { confirm: true }),
      WriteNotAllowedError
    );
  });

  test("blocks when env flag is set but confirm is missing", () => {
    process.env.MCP_MS_ALLOW_WRITES = "1";
    assert.throws(
      () => assertWriteAllowed("delete_user", {}),
      WriteNotAllowedError
    );
  });

  test("blocks when env flag is set but confirm is false", () => {
    process.env.MCP_MS_ALLOW_WRITES = "1";
    assert.throws(
      () => assertWriteAllowed("delete_user", { confirm: false }),
      WriteNotAllowedError
    );
  });

  test("blocks when confirm:true but env flag is some other value", () => {
    process.env.MCP_MS_ALLOW_WRITES = "true"; // not the literal "1"
    assert.throws(
      () => assertWriteAllowed("delete_user", { confirm: true }),
      WriteNotAllowedError
    );
  });

  test("allows when both env flag is \"1\" and confirm is true", () => {
    process.env.MCP_MS_ALLOW_WRITES = "1";
    assert.doesNotThrow(() => assertWriteAllowed("delete_user", { confirm: true }));
  });
});
