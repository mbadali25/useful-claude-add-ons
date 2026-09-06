// Tests for the stale-build guard. Plain .mjs against a throwaway tree under
// os.tmpdir(): the guard's whole job is to reason about mtimes in a package
// layout, so a fixture is the only way to exercise it without editing a real
// package's sources to move their timestamps.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";

import { checkPackage, newestMtime } from "../check-dist-fresh.mjs";

const CORE = "@badali404/mcp-ms-core";

/** A two-package workspace: `core`, and `consumer` which depends on it. */
function fixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "dist-fresh-"));
  const packages = path.join(root, "packages");
  for (const [name, manifest] of [
    ["core", { name: CORE, dependencies: {} }],
    ["consumer", { name: "consumer", dependencies: { [CORE]: "0.2.0" } }],
  ]) {
    const dir = path.join(packages, name);
    fs.mkdirSync(path.join(dir, "src"), { recursive: true });
    fs.mkdirSync(path.join(dir, "test"), { recursive: true });
    fs.mkdirSync(path.join(dir, "dist", "src"), { recursive: true });
    fs.writeFileSync(path.join(dir, "package.json"), JSON.stringify(manifest));
    fs.writeFileSync(path.join(dir, "src", "index.ts"), "export const a = 1;\n");
    fs.writeFileSync(path.join(dir, "test", "index.test.ts"), "// test\n");
    fs.writeFileSync(path.join(dir, "dist", "src", "index.js"), "export const a = 1;\n");
  }
  // A plausible built state: every dist newer than every src. Written here
  // rather than per-test so each test moves ONE timestamp and the reason it
  // fails is unambiguous.
  for (const name of ["core", "consumer"]) {
    touch(path.join(packages, name, "dist", "src", "index.js"), 60);
  }
  return { packages, core: path.join(packages, "core"),
    consumer: path.join(packages, "consumer") };
}

/** Set one file's mtime `seconds` from now, so ordering is explicit. */
function touch(file, seconds) {
  const when = new Date(Date.now() + seconds * 1000);
  fs.utimesSync(file, when, when);
}

test("a freshly built package passes", () => {
  const { packages, consumer } = fixture();
  assert.equal(checkPackage(consumer, packages).ok, true);
});

test("equal timestamps are STALE, not fresh", () => {
  // Measured, not assumed: after `npm run build` in this repo every package's
  // newest dist/*.js is strictly newer than its newest src/*.ts (11.9s for
  // core), and mtimes carry sub-millisecond fractions. tsc reads before it
  // writes, so the strict ordering is structural. Accepting equal would let a
  // real edit landing in the same coarse tick as an older build read as fresh.
  const { packages, consumer } = fixture();
  const when = new Date(Date.now());
  for (const rel of [["src", "index.ts"], ["dist", "src", "index.js"]]) {
    fs.utimesSync(path.join(consumer, ...rel), when, when);
  }
  assert.equal(checkPackage(consumer, packages).ok, false);
});

test("its own edited source makes it stale", () => {
  const { packages, consumer } = fixture();
  touch(path.join(consumer, "src", "index.ts"), 120);
  const result = checkPackage(consumer, packages);
  assert.equal(result.ok, false);
  assert.match(result.reason, /consumer\/src/);
});

test("an edited test source makes it stale too", () => {
  const { packages, consumer } = fixture();
  touch(path.join(consumer, "test", "index.test.ts"), 120);
  const result = checkPackage(consumer, packages);
  assert.equal(result.ok, false);
  assert.match(result.reason, /consumer\/test/);
});

test("a stale CORE fails a consumer whose own build is the NEWEST thing", () => {
  // The finding this file exists for. Comparing the consumer's dist against
  // core/src passes here -- the consumer's dist is newer than everything --
  // while core/dist, which the consumer actually imports at runtime, is
  // older than the core sources it was compiled from.
  const { packages, consumer } = fixture();
  touch(path.join(packages, "core", "src", "index.ts"), 120);
  touch(path.join(consumer, "dist", "src", "index.js"), 240);

  const result = checkPackage(consumer, packages);
  assert.equal(result.ok, false, "a consumer of a stale core must not pass");
  assert.match(result.reason, /core\/src/);
  assert.match(result.reason, /imports it at runtime/);
});

test("a consumer of a core with no build at all fails", () => {
  const { packages, consumer } = fixture();
  fs.rmSync(path.join(packages, "core", "dist"), { recursive: true });
  const result = checkPackage(consumer, packages);
  assert.equal(result.ok, false);
  assert.match(result.reason, /dist\/ does not exist/);
  assert.match(result.reason, /imports it at runtime/);
});

test("core itself is not checked against core twice", () => {
  const { packages, core } = fixture();
  assert.equal(checkPackage(core, packages).ok, true);
  // And a stale core fails on its own account, with no consumer suffix.
  touch(path.join(core, "src", "index.ts"), 120);
  const result = checkPackage(core, packages);
  assert.equal(result.ok, false);
  assert.doesNotMatch(result.reason, /imports it at runtime/);
});

test("a missing dist is a failure, not a pass", () => {
  const { packages, consumer } = fixture();
  fs.rmSync(path.join(consumer, "dist"), { recursive: true });
  const result = checkPackage(consumer, packages);
  assert.equal(result.ok, false);
  assert.match(result.reason, /dist\/ does not exist/);
});

test("a dist directory holding no .js is a failure", () => {
  // `npm run clean` leaves the directory in some layouts. An empty dist has a
  // newest-mtime of 0, which would compare older than everything -- but saying
  // "older than src" for a build that never happened sends the reader looking
  // at timestamps instead of at the missing output.
  const { packages, consumer } = fixture();
  fs.rmSync(path.join(consumer, "dist", "src", "index.js"));
  const result = checkPackage(consumer, packages);
  assert.equal(result.ok, false);
  assert.match(result.reason, /holds no \.js/);
});

test("a missing src/ is a failure, not an empty comparison", () => {
  // The fail-open shape: an absent source directory contributing mtime 0
  // compares older than any dist and reads as fresh, so the guard passes
  // having compared nothing.
  const { packages, consumer } = fixture();
  fs.rmSync(path.join(consumer, "src"), { recursive: true });
  const result = checkPackage(consumer, packages);
  assert.equal(result.ok, false);
  assert.match(result.reason, /src\/ does not exist/);
});

test("a missing test/ is allowed -- it is genuinely optional", () => {
  const { packages, consumer } = fixture();
  fs.rmSync(path.join(consumer, "test"), { recursive: true });
  assert.equal(checkPackage(consumer, packages).ok, true);
});

test("newestMtime reports a missing directory as missing, not as 0", () => {
  const { consumer } = fixture();
  const absent = newestMtime(path.join(consumer, "nope"), ".ts");
  assert.deepEqual(absent, { mtime: 0, missing: true });
  const present = newestMtime(path.join(consumer, "src"), ".ts");
  assert.equal(present.missing, false);
  assert.ok(present.mtime > 0);
});

test("newestMtime rethrows a read error that is not ENOENT", () => {
  // An unreadable directory is an unknown. Returning 0 would make it compare
  // older than everything and read as fresh -- the guard passing on a tree it
  // could not see.
  //
  // The target is a FILE, which gives ENOTDIR on both platforms. A path
  // *under* a file was the first attempt and is wrong: Windows answers ENOENT
  // there, so the test passed on Linux and failed here -- caught by running
  // it, which is the only way this class gets caught.
  const { consumer } = fixture();
  const notADir = path.join(consumer, "src", "index.ts");
  assert.throws(() => newestMtime(notADir, ".ts"),
    (err) => err.code === "ENOTDIR");
});

test("newestMtime only counts the extension it was asked for", () => {
  const { consumer } = fixture();
  const stray = path.join(consumer, "src", "notes.md");
  fs.writeFileSync(stray, "not source\n");
  touch(stray, 600);
  const ts = newestMtime(path.join(consumer, "src"), ".ts");
  assert.ok(ts.mtime < fs.statSync(stray).mtimeMs);
});
