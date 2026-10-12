#!/usr/bin/env node
/*
 * Start the Angular language server (@angular/language-server, `ngserver`)
 * with the two probe locations it refuses to start without.
 *
 * ngserver exits at once ("Failed to resolve 'typescript/lib/tsserverlibrary'
 * ... from []") unless --tsProbeLocations and --ngProbeLocations name a
 * directory from which `typescript` and `@angular/language-service` resolve.
 * The package ships its own copy of both, but where a global npm package
 * lives differs on every machine and operating system, so that path cannot be
 * written into a static LSP config. This file finds it at start-up instead.
 *
 * Probe order, the same as the VS Code extension's: the project first (its
 * own typescript / @angular/language-service, when node_modules is there),
 * then the copies bundled with the language server. ngserver skips a
 * location whose package is older than it supports and moves to the next.
 *
 * The server is loaded into THIS process rather than spawned, so stdio is the
 * server's own and there is no child to forward signals to or to leak.
 *
 * Not handled: a directory whose path contains a comma. ngserver splits each
 * probe list on "," and offers no escape, so such a location is dropped with
 * a note on stderr rather than passed through as two wrong paths.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const PACKAGE = path.join('@angular', 'language-server');

function isServerDir(dir) {
  try {
    const manifest = JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf8'));
    return manifest.name === '@angular/language-server' && fs.existsSync(path.join(dir, 'index.js'));
  } catch (_err) {
    return false;
  }
}

function fromPath() {
  const names = process.platform === 'win32' ? ['ngserver.cmd', 'ngserver.ps1', 'ngserver'] : ['ngserver'];
  for (const dir of (process.env.PATH || '').split(path.delimiter)) {
    if (!dir) continue;
    for (const name of names) {
      const shim = path.join(dir, name);
      if (!fs.existsSync(shim)) continue;
      const candidates = [
        // Windows npm prefix: shims sit beside node_modules.
        path.join(dir, 'node_modules', PACKAGE),
        // POSIX npm prefix: <prefix>/bin/ngserver, <prefix>/lib/node_modules.
        path.join(dir, '..', 'lib', 'node_modules', PACKAGE),
      ];
      try {
        // POSIX: the shim is a symlink to <package>/bin/ngserver.
        candidates.unshift(path.dirname(path.dirname(fs.realpathSync(shim))));
      } catch (_err) {
        // unreadable link: the two prefix guesses above still apply
      }
      for (const candidate of candidates) {
        if (isServerDir(candidate)) return path.resolve(candidate);
      }
    }
  }
  return null;
}

function fromNpm() {
  // npm is npm.cmd on Windows, which only a shell can start.
  const done = spawnSync('npm root -g', {
    shell: true, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], timeout: 20000,
  });
  if (done.status !== 0 || !done.stdout) return null;
  const candidate = path.join(done.stdout.trim(), PACKAGE);
  return isServerDir(candidate) ? candidate : null;
}

function findServer() {
  const override = process.env.ANGULAR_LANGUAGE_SERVER_DIR;
  if (override) {
    if (isServerDir(override)) return path.resolve(override);
    process.stderr.write(
      `angular-lsp: ANGULAR_LANGUAGE_SERVER_DIR is '${override}', which is not an @angular/language-server package directory\n`);
    return null;
  }
  return fromPath() || fromNpm();
}

function probeList(dirs) {
  const kept = [];
  for (const dir of dirs) {
    if (!dir || kept.includes(dir)) continue;
    if (dir.includes(',')) {
      process.stderr.write(`angular-lsp: skipping probe location with a comma in its path: ${dir}\n`);
      continue;
    }
    kept.push(dir);
  }
  return kept.join(',');
}

function main() {
  const server = findServer();
  if (!server) {
    process.stderr.write(
      'angular-lsp: cannot find @angular/language-server. Install it with ' +
      "'npm install -g @angular/language-server' (it puts 'ngserver' on PATH), or set " +
      'ANGULAR_LANGUAGE_SERVER_DIR to the package directory.\n');
    process.exit(1);
  }
  const project = process.env.CLAUDE_PROJECT_DIR || process.cwd();
  const passed = process.argv.slice(2);
  const args = passed.slice();
  // A caller that names its own locations keeps them.
  if (!passed.includes('--tsProbeLocations')) args.push('--tsProbeLocations', probeList([project, server]));
  if (!passed.includes('--ngProbeLocations')) args.push('--ngProbeLocations', probeList([project, server]));
  const entry = path.join(server, 'index.js');
  // ngserver reads its options from process.argv, so they are set before it loads.
  process.argv = [process.argv[0], entry, ...args];
  require(entry);
}

main();
