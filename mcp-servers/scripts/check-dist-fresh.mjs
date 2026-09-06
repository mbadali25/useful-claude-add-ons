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
// A consumer is checked by checking CORE ITSELF, recursively -- not by
// comparing the consumer's `dist` against `core/src`. The difference is the
// whole finding: a consumer imports `core/dist` at RUNTIME, so what has to be
// current is core's own build against core's own sources. Comparing the
// consumer's `dist` to `core/src` passes the moment the consumer is rebuilt,
// even though `core/dist` is untouched and still stale -- preserving exactly
// the failure this file exists to stop.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const CORE = "@badali404/mcp-ms-core";

/**
 * Newest mtime under `dir` for files matching `ext`.
 *
 * `{ mtime, missing }` -- and it THROWS on any read error that is not
 * "does not exist". A directory that cannot be read is an unknown, and an
 * unknown returned as `0` compares older than everything and reads as fresh:
 * the guard would then pass having checked nothing, which is the failure mode
 * it exists to prevent, wearing its own label. `missing` is a separate value
 * for the same reason -- the caller decides whether an absent directory is
 * legitimate (`test/`) or a broken tree (`src/`), and it cannot decide that
 * from a number.
 */
export function newestMtime(dir, ext) {
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch (err) {
    if (err.code === "ENOENT") return { mtime: 0, missing: true };
    throw err;
  }
  let newest = 0;
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      newest = Math.max(newest, newestMtime(full, ext).mtime);
    } else if (entry.name.endsWith(ext)) {
      newest = Math.max(newest, fs.statSync(full).mtimeMs);
    }
  }
  return { mtime: newest, missing: false };
}

function fail(reason) {
  return { ok: false, reason };
}

/** One package against its OWN sources. Nothing about its dependencies. */
function checkOwnBuild(pkgDir, name) {
  const dist = path.join(pkgDir, "dist");
  const built = newestMtime(dist, ".js");
  if (built.missing) return fail(`${name}: dist/ does not exist`);
  if (built.mtime === 0) return fail(`${name}: dist/ holds no .js`);

  const src = newestMtime(path.join(pkgDir, "src"), ".ts");
  if (src.missing) return fail(`${name}: src/ does not exist`);

  // `test/` is genuinely optional; `src/` is not. Both are compiled into
  // dist/ when present, so both gate the build.
  const tests = newestMtime(path.join(pkgDir, "test"), ".ts");

  // STRICT. Equal mtimes are stale, not fresh.
  //
  // An earlier revision accepted equal as fresh, reasoning that a build fast
  // enough to land in the same filesystem tick as its edit would otherwise
  // fail every time -- and a check that cries wolf on a correct tree gets
  // disabled. Measured on this repo instead of argued: after `npm run build`,
  // every package's newest dist/*.js is strictly newer than its newest
  // src/*.ts, by 11.9 seconds for core and more elsewhere, with mtimes carrying
  // sub-millisecond fractions. tsc reads the source before it writes the
  // output, so on any filesystem whose resolution is finer than a build, that
  // ordering is structural rather than lucky. Accepting equal would leave a
  // real edit landing in the same coarse tick as an older build reading as
  // fresh -- the guard passing on exactly the input it was built to catch.
  const stale = [];
  if (src.mtime >= built.mtime) stale.push("src");
  if (!tests.missing && tests.mtime >= built.mtime) stale.push("test");
  if (stale.length) {
    return fail(`${name}: compiled output is not newer than `
      + stale.map((d) => `${path.basename(pkgDir)}/${d}`).join(", "));
  }
  return { ok: true, reason: null };
}

/**
 * `{ ok, reason }` for one package, including every workspace dependency it
 * imports the build output of.
 */
export function checkPackage(pkgDir, packagesDir) {
  const manifest = JSON.parse(
    fs.readFileSync(path.join(pkgDir, "package.json"), "utf8"));

  const own = checkOwnBuild(pkgDir, manifest.name);
  if (!own.ok) return own;

  const deps = { ...manifest.dependencies, ...manifest.devDependencies };
  if (manifest.name !== CORE && Object.hasOwn(deps, CORE)) {
    const core = checkOwnBuild(path.join(packagesDir, "core"), CORE);
    if (!core.ok) {
      return fail(`${core.reason} -- and ${manifest.name} imports it at runtime`);
    }
  }
  return { ok: true, reason: null };
}

function main() {
  const pkgDir = process.argv[2] ? path.resolve(process.argv[2]) : process.cwd();
  const packagesDir = path.dirname(pkgDir);
  let result;
  try {
    result = checkPackage(pkgDir, packagesDir);
  } catch (err) {
    // An unreadable directory is not a pass. Say what could not be read.
    process.stderr.write(`\nSTALE-BUILD CHECK COULD NOT RUN -- ${err.message}\n`
      + "This is not a pass: the build's freshness is unknown, so the tests "
      + "below it would prove nothing.\n\n");
    return 1;
  }
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
