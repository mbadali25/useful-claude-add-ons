# Publishing mcp-servers to npm

How to get `@mbadali/mcp-ms-core` and the four servers (`mcp-msgraph`, `mcp-intune`,
`mcp-o365-user`, `mcp-o365-admin`) onto the npm registry, so the `npx` one-liners in
`README.md` actually resolve. Every command below is plain npm/git/gh — identical on
Windows and Linux, no OS-specific variants.

## 1. One-time npm setup

1. Create an npm account at <https://www.npmjs.com/signup> if you don't have one.
2. Get the `@mbadali` scope. If your npm username is literally `mbadali`, you already
   own it. Otherwise create an **organization** named `mbadali`: npmjs.com → avatar →
   **Add Organization** → `mbadali` → free tier.
3. Scoped packages (`@mbadali/...`) publish **private by default** on the free tier —
   that's why every `npm publish` below passes `--access public`. Drop it and the
   publish fails, or silently creates a private package `npx` can't install.

## 2. Token for CI

1. npmjs.com → avatar → **Access Tokens** → **Generate New Token** → **Granular
   Access Token**, Read+Write scoped to `@mbadali`. An **Automation** token also works
   and additionally bypasses OTP/2FA on publish, which matters because CI can't answer
   a 2FA prompt.
2. Copy it now — npm shows it once. Then:

   ```bash
   gh secret set NPM_TOKEN --repo mbadali25/useful-claude-add-ons
   ```

   (paste the token when prompted).

**This token can publish new versions of these packages as you.** Treat it like a
password — never commit it, never pass it as a script argument.

## 3. Publish via CI (the intended path)

Bump versions first if this isn't the first publish (§5). Then tag and push:

```bash
git tag mcp-servers-v0.1.0
git push origin mcp-servers-v0.1.0
```

Any `mcp-servers-v*` tag push triggers
[`.github/workflows/publish-mcp-servers.yml`](../.github/workflows/publish-mcp-servers.yml):
`npm ci` + `npm test` on the workspace, then `npm publish --provenance --access public`
per package, in order — `@mbadali/mcp-ms-core` **first** (the four servers pin an exact
version of it, so it must exist on the registry before they publish), then `mcp-msgraph`,
`mcp-intune`, `mcp-o365-user`, `mcp-o365-admin`. `--provenance` needs the job's
`id-token: write` permission (already set) for GitHub's OIDC token to sign the
attestation — CI-only, doesn't work from a laptop.

Watch it: `gh run watch`, or the **Actions** tab, workflow "Publish MCP servers
(Microsoft)".

## 4. Publish manually (fallback)

Only if CI is broken or you need a one-off. Drop `--provenance` — it's CI-only.

```bash
npm login
cd mcp-servers/packages/core && npm publish --access public
```

Core **must** land first — wait for it to succeed, and confirm each server's pinned
`"@mbadali/mcp-ms-core"` version in `package.json` matches what you just published
(it's an exact pin, not a range — a mismatch means `npm install` can't resolve it).
Then the four servers, any order relative to each other:

```bash
cd ../graph && npm publish --access public
cd ../intune && npm publish --access public
cd ../o365-user && npm publish --access public
cd ../o365-admin && npm publish --access public
```

## 5. Releasing an update

1. Bump `version` in each **changed** package's `package.json` (semver). `npm version
   patch` (run inside that package directory) bumps + commits + tags for you; add
   `--no-git-tag-version` to just bump and commit everything together below.
2. If `packages/core` changed, also bump the `"@mbadali/mcp-ms-core"` pin in every
   server's `package.json` that depends on it, to match core's new version.
3. Commit, tag with the new number, push:

   ```bash
   git add mcp-servers/packages/*/package.json
   git commit -m "mcp-servers: bump versions for release"
   git tag mcp-servers-v0.2.0
   git push origin main mcp-servers-v0.2.0
   ```

## 6. Verify after first publish

```bash
npm view @mbadali/mcp-ms-core version
npx -y @mbadali/mcp-msgraph@latest doctor
```

`doctor` should fail on missing `MS_ADMIN_*` (or succeed if you have them set) — either
way, reaching that error proves `npx` resolved and ran the published package, not a
stale local build. Then register for real:

```bash
claude mcp add mcp-msgraph -- npx -y @mbadali/mcp-msgraph@latest
claude mcp add mcp-intune -- npx -y @mbadali/mcp-intune@latest
claude mcp add mcp-o365-user -- npx -y @mbadali/mcp-o365-user@latest
claude mcp add mcp-o365-admin -- npx -y @mbadali/mcp-o365-admin@latest
```

## 7. Troubleshooting

- **`402 Payment Required`** — missing `--access public` on a scoped package. Add it.
- **`403 Forbidden`** — token lacks publish rights to `@mbadali`, or 2FA is blocking a
  non-interactive publish. Use a Granular token scoped to `@mbadali` (Read+Write) or an
  Automation token, which bypasses 2FA.
- **`ENEEDAUTH` in CI** — the `NPM_TOKEN` secret is missing or misnamed. Check with
  `gh secret list --repo mbadali25/useful-claude-add-ons` and re-set it (§2).
- **Publish succeeds but `npx` runs the old version** — it cached. Pin `@latest`
  explicitly (every command above does) or clear the cache: `npx clear-npx-cache`
  (or delete `~/.npm/_npx` by hand if that command isn't available).
