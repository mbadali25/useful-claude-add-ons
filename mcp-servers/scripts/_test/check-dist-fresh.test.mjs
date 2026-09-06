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
  return { packages, core: path.join(packages, "core"),
    consumer: path.join(packages, "consumer") };
}

/** Set one file's mtime `seconds` after now, so ordering is explicit. */
function touch(file, seconds) {
  const when = new Date(Date.now() + seconds * 1000);
  fs.utimesSync(file, when, when);
}

test("a freshly built package passes", () => {
  const { packages, consumer } = fixture();
  touch(path.join(consumer, "dist", "src", "index.js"), 10);
  assert.equal(checkPackage(consumer, packages).ok, true);
});

test("equal timestamps count as fresh", () => {
  const { packages, consumer } = fixture();
  const when = new Date(Date.now());
  for (const rel of [["src", "index.ts"], ["test", "index.test.ts"],
    ["dist", "src", "index.js"]]) {
    fs.utimesSync(path.join(consumer, ...rel), when, when);
  }
  fs.utimesSync(path.join(packages, "core", "src", "index.ts"), when, when);
  assert.equal(checkPackage(consumer, packages).ok, true,
    "a build landing in the same tick as its edit is normal, not stale");
});

test("its own edited source makes it stale", () => {
  const { packages, consumer } = fixture();
  touch(path.join(consumer, "src", "index.ts"), 10);
  const result = checkPackage(consumer, packages);
  assert.equal(result.ok, false);
  assert.match(result.reason, /consumer\/src/);
});

test("an edited test source makes it stale too", () => {
  const { packages, consumer } = fixture();
  touch(path.join(consumer, "test", "index.test.ts"), 10);
  assert.equal(checkPackage(consumer, packages).ok, false);
});

test("an edited CORE source makes a consumer stale", () => {
  // The case the entry was actually about: the consumer's own build is
  // current, and it imports last week's core.
  const { packages, consumer } = fixture();
  touch(path.join(packages, "core", "src", "index.ts"), 10);
  const result = checkPackage(consumer, packages);
  assert.equal(result.ok, false);
  assert.match(result.reason, /core\/src/);
});

test("core itself is not compared against core", () => {
  // Otherwise core would report itself stale against its own sources through
  // the consumer branch, which is the same directory twice.
  const { packages, core } = fixture();
  touch(path.join(core, "dist", "src", "index.js"), 10);
  assert.equal(checkPackage(core, packages).ok, true);
  assert.equal(checkPackage(core, packages).sources.length, 2);
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
  // newest-mtime of 0, which would compare as older than everything -- but
  // saying "older than src" for a build that never happened sends the reader
  // looking at timestamps instead of at the missing output.
  const { packages, consumer } = fixture();
  fs.rmSync(path.join(consumer, "dist", "src", "index.js"));
  const result = checkPackage(consumer, packages);
  assert.equal(result.ok, false);
  assert.match(result.reason, /holds no \.js/);
});

test("newestMtime answers 0 for a directory that is not there", () => {
  const { consumer } = fixture();
  assert.equal(newestMtime(path.join(consumer, "nope"), ".ts"), 0);
});

test("newestMtime only counts the extension it was asked for", () => {
  const { consumer } = fixture();
  const stray = path.join(consumer, "src", "notes.md");
  fs.writeFileSync(stray, "not source\n");
  touch(stray, 60);
  const ts = newestMtime(path.join(consumer, "src"), ".ts");
  assert.ok(ts < fs.statSync(stray).mtimeMs);
});
