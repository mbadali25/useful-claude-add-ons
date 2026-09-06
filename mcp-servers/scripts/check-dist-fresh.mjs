#!/usr/bin/env node
// Refuse to run a package's tests against compiled JS older than the
// TypeScript it was compiled from.
//
// Every package here points `main`, `types` and `exports` at `./dist/src/...`,
// so nothing imports a `.ts` file at runtime -- the tests included. Editing
// `src` and re-running the tests therefore exercises the PREVIOUS build, and
// the pass it prints is about code that is no longer in the tree. Nothing in
// the edit path said so.
//
// The hole is narrower than it looks, and naming it precisely matters: `dist/`
// is untracked, and the root `test` script is `npm run build && npm run test
// --workspaces`, where the root `build` builds `core` first. CI therefore
// cannot test stale JS. What can is a per-package invocation -- `npm test -w
// packages/graph` after editing `packages/core/src` -- which skips the root
// build entirely. That is the case this check covers, and it is wired as each
// package's `pretest` so it fires exactly there.
//
// A consumer's sources include core's, because a consumer imports core's build
// output. A stale core is invisible from inside the consumer otherwise: its
// own dist is current, its own tests compile, and the behaviour under test is
// last week's.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const CORE = "@badali404/mcp-ms-core";

/** Newest mtime under `dir` for files matching `ext`, or 0 when there are none. */
export function newestMtime(dir, ext) {
  let newest = 0;
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return 0; // A directory that does not exist contributes nothing.
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      newest = Math.max(newest, newestMtime(full, ext));
    } else if (entry.name.endsWith(ext)) {
      newest = Math.max(newest, fs.statSync(full).mtimeMs);
    }
  }
  return newest;
}

/**
 * `{ ok, reason, sources }` for one package directory.
 *
 * Equal timestamps are FRESH, not stale. A build fast enough to land in the
 * same filesystem tick as the edit that triggered it is a normal outcome on a
 * small package, and a strict `>=` would fail it every time -- a check that
 * cries wolf on a correct tree gets disabled, which is worse than not having
 * one.
 */
export function checkPackage(pkgDir, packagesDir) {
  const manifest = JSON.parse(
    fs.readFileSync(path.join(pkgDir, "package.json"), "utf8"));
  const dist = path.join(pkgDir, "dist");
  if (!fs.existsSync(dist)) {
    return { ok: false, reason: `${manifest.name}: dist/ does not exist`, sources: [] };
  }

  const sources = [path.join(pkgDir, "src"), path.join(pkgDir, "test")];
  const deps = { ...manifest.dependencies, ...manifest.devDependencies };
  if (manifest.name !== CORE && Object.hasOwn(deps, CORE)) {
    sources.push(path.join(packagesDir, "core", "src"));
  }

  const builtAt = newestMtime(dist, ".js");
  if (builtAt === 0) {
    return { ok: false, reason: `${manifest.name}: dist/ holds no .js`, sources };
  }
  const stale = sources.filter((dir) => newestMtime(dir, ".ts") > builtAt);
  if (stale.length) {
    return {
      ok: false,
      reason: `${manifest.name}: compiled output is older than `
        + stale.map((d) => path.relative(packagesDir, d).replace(/\\/g, "/")).join(", "),
      sources,
    };
  }
  return { ok: true, reason: null, sources };
}

function main() {
  const pkgDir = process.argv[2] ? path.resolve(process.argv[2]) : process.cwd();
  const packagesDir = path.dirname(pkgDir);
  const result = checkPackage(pkgDir, packagesDir);
  if (result.ok) return 0;
  process.stderr.write(
    `\nSTALE BUILD -- ${result.reason}.\n`
    + "These tests import dist/, so running them now would test the previous "
    + "build and report a pass about code that is not in the tree.\n"
    + "Run `npm run build` from mcp-servers/ (it builds core first, then every "
    + "workspace) and try again.\n\n");
  return 1;
}

// Run-as-script detection by resolved PATH, not by string-building a file://
// URL: on Windows the two forms differ (`file:///C:/...` vs `file://C:\...`),
// so the naive comparison is false on exactly the platform half the CI matrix
// runs, and the check would silently never execute there.
if (process.argv[1]
    && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exit(main());
}
