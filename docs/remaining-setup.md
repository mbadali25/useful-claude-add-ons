# Remaining setup — the steps only you can do

Everything merged on 2026-08-28 (crew 0.11.3, obsidian-vault 0.1.2, mcp-servers)
runs from this repo, but four workstreams need credentials, consent, or a yes
that only you can give. This is the complete, ordered walkthrough. Every command
is copy-pasteable; Windows and Linux forms are identical unless marked.

Do them in this order — 1 and 2 are independent, 3 depends on nothing but an
Entra tenant, 4 is optional polish.

---

## 1. Install the obsidian-vault plugin and repair the vault

Your vault has three live defects found on 2026-08-28, and the fix ships in the
plugin's `doctor` command (your call — "fold into the plugin PR").

### 1a. Install and initialize

```bash
claude plugin install obsidian-vault@useful-claude-add-ons
```

Restart Claude Code (hooks are cached at load), then in a session:

```
/obsidian-vault:init
```

It detects `C:\repos\claude-memories` from Obsidian's own registry, configures
the Local REST API bridge, registers the `obsidian-memory` MCP server, and
writes `~/.claude/obsidian/config.json`. Answer the companion-plugin
recommendations as you like — each install asks its own yes.

Then add the codegraphs vault as a second named vault:

```
/obsidian-vault:init codegraphs C:\repos\claude-memories-codegraphs
```

That registers `obsidian-codegraphs` on port 27125 with `layout: org/repo`.
The bridge for it is live only while Obsidian has that vault open in its own
window.

### 1b. Run doctor — this is the actual repair

```
/obsidian-vault:doctor
```

It will find and walk you through fixing, with a yes per repair:

1. **The vault is not a git repository, but obsidian-git thinks it is.**
   `autoSaveInterval`/`autoPushInterval` are 15 — the plugin has been trying to
   commit and push into a `.git` that does not exist since at least 08-24.
   The repair: `git init` in the vault, `git remote add origin
   git@github.com:mbadali25/claude-memories.git` (create that repo on GitHub
   first if it does not exist: `gh repo create mbadali25/claude-memories
   --private`), initial commit, push. From then on obsidian-git's 15-minute
   auto-backup actually backs up.
2. **The vault CLAUDE.md's "Sync *and* git" section describes a git posture
   the filesystem does not have.** Doctor offers the corrected text; it never
   silently rewrites. If you do 1 above, the section becomes true again and
   only needs the date updated.
3. **The gardener last ran 2026-08-24.** Doctor re-runs it and points you at
   the `obsidian-scheduling` skill to schedule it — on Windows:

   ```powershell
   # nightly at 02:30, per the obsidian-scheduling skill
   schtasks /Create /TN "obsidian-gardener" /SC DAILY /ST 02:30 `
     /TR "pwsh -NoProfile -File C:\repos\claude-memories\.claude\gardener.ps1"
   ```

4. It will also note `wiki/maps/` is empty — run `/obsidian-vault:map <area>`
   for the two or three areas you care about, and `/obsidian-vault:canvas
   <topic>` when a picture would help.

### 1c. Optional: plugin set review

```
/obsidian-vault:optimize
```

Reports what your 15 community plugins cost on a vault this size and proposes
changes. Every removal stops for its own yes; nothing is uninstalled behind
your back.

---

## 2. Publish the MCP servers to npm (unlocks `npx` installs)

Full detail in [`mcp-servers/PUBLISHING.md`](../mcp-servers/PUBLISHING.md).
The short path:

1. **Own the scope.** If your npm username is `badali404`, done. Otherwise
   npmjs.com → avatar → Add Organization → `badali404` → free tier.
2. **Token.** npmjs.com → Access Tokens → Generate New Token → Granular
   (Read+Write on `@badali404`) or Automation (bypasses 2FA in CI). Then:

   ```bash
   gh secret set NPM_TOKEN --repo mbadali25/useful-claude-add-ons
   ```

3. **Tag.**

   ```bash
   git tag mcp-servers-v0.1.0
   git push origin mcp-servers-v0.1.0
   ```

   The workflow publishes core first, then the four servers, with provenance.
   Watch: `gh run watch`.
4. **Verify.**

   ```bash
   npm view @badali404/mcp-ms-core version
   npx -y @badali404/mcp-msgraph@latest doctor
   ```

   Reaching doctor's "missing MS_ADMIN_*" error proves npx resolved the
   published package. Until you publish, the interim path works today:

   ```bash
   cd mcp-servers && npm install && npm run build
   cd packages/graph && npm install -g .
   claude mcp add mcp-msgraph -- mcp-msgraph
   ```

---

## 3. Auth for the MCP servers

`mcp-o365-user` (your own mail/calendar/files) is unchanged and always needs
its own app registration — 3a below. The other three
(`mcp-msgraph`/`mcp-intune`/`mcp-o365-admin`) now authenticate through a
chain (`packages/core/src/adminAuth.ts`): client secret, then `az login`,
then device code, tried in that order and controllable with `MS_ADMIN_AUTH`.
Pick the tier below that matches what you're doing — they aren't mutually
exclusive, and you can start at tier 1 today and add tier 3 later without
touching anything you've already set up.

### 3a. User-scope app (for `mcp-o365-user` — your own mail/calendar/files)

Entra ID → App registrations → New registration:

1. Name it e.g. `mcp-o365-user`, single tenant, no redirect URI.
2. Authentication → **Allow public client flows: Yes** (device code needs it).
3. API permissions → Microsoft Graph → **Delegated**: `User.Read`,
   `Mail.ReadWrite`, `Mail.Send`, `Calendars.ReadWrite`, `Files.Read`.
   Grant admin consent if your tenant requires it for these.
4. Record the Application (client) ID, then set (user-level env):

   ```powershell
   setx MS_USER_CLIENT_ID "<app id>"
   setx MS_USER_TENANT_ID "<tenant id>"   # optional; defaults to 'organizations'
   ```

   Linux: `export` in your shell profile.
5. First tool call triggers a device-code sign-in — you approve it in a
   browser as yourself.

### 3b. Admin-scope servers — tier 1: nothing but `az login` (fastest)

If you're already signed in with the Azure CLI (`az login`) as a Global
Administrator or with equivalent Graph access, `mcp-msgraph`, `mcp-intune`,
and `mcp-o365-admin` need **no setup at all** — no app registration, no
secret, no env vars. Just register and run:

```bash
mcp-msgraph doctor      # or: npx -y @badali404/mcp-msgraph@latest doctor
```

`doctor` should report `auth method: cli`, `token type: delegated`. What you
actually get is bounded by what the "Microsoft Azure CLI" app itself is
consented for in this tenant, intersected with your own role — being Global
Admin does not add scopes that app was never granted; Graph's delegated model
is the *more restrictive* of the two, not their union. In many tenants that
app's own consented set is broad (well beyond the tool-by-tool scope list in
the README), which is why this tier often works for more than it looks like
it should — but it's the app's consent doing that, not your role alone. What
you don't get at this tier: any Graph permission that app hasn't been
consented for (some tenants exclude Intune scopes from it), and any endpoint
that flatly requires an app-only token regardless of who's signed in. If
`doctor` authenticates but a specific tool call 403s, that's tier 2 or 3.

### 3c. Admin-scope servers — tier 2: device code with a public-client app (no secret)

One step up from tier 1, still no client secret to manage. Use this when
tier 1's Azure CLI app doesn't have the Graph scopes a tool needs, but you
still don't want a confidential-client app with a secret sitting in your
environment.

1. Entra ID → App registrations → New registration, e.g. `mcp-ms-admin-device`,
   single tenant.
2. Authentication → **Allow public client flows: Yes**.
3. API permissions → Microsoft Graph → **Delegated** — grant exactly the
   scopes the tools you'll use need (the same names as the Application
   permissions listed in tier 3 below, but as Delegated), then **Grant
   admin consent**.
4. Record the Application (client) ID, then set:

   ```powershell
   setx MS_ADMIN_CLIENT_ID "<app id>"
   setx MS_ADMIN_TENANT_ID "<tenant id>"   # optional; defaults to 'organizations'
   # do NOT set MS_ADMIN_CLIENT_SECRET -- its absence is what selects this tier
   ```

5. `doctor` now falls through tier 1's `cli` link (unless you're signed in
   with `az login` too, in which case that still wins — see the chain order
   in the README) to `device`, prompting a one-time sign-in per process
   launch.

### 3d. Admin-scope servers — tier 3: full app-only registration (unattended/automation)

The tier to use for anything unattended, scheduled, or where you want the
server's access bounded by exactly what was consented — independent of
which human is signed in. This was the only option before the auth chain
existed, and still works exactly as before.

New registration, e.g. `mcp-ms-admin`, single tenant:

1. Certificates & secrets → New client secret. Copy it immediately.
2. API permissions → Microsoft Graph → **Application** — grant only what the
   tools you will use need, then **Grant admin consent**:
   - msgraph reads: `User.Read.All`, `Group.Read.All`; writes add
     `User.ReadWrite.All`, `GroupMember.ReadWrite.All`
   - intune reads: `DeviceManagementManagedDevices.Read.All`,
     `DeviceManagementConfiguration.Read.All`; writes add
     `DeviceManagementManagedDevices.PrivilegedOperations.All`,
     `DeviceManagementConfiguration.ReadWrite.All`
   - o365-admin reads: `User.Read.All`, `MailboxSettings.Read`; writes add
     `User.ReadWrite.All`
   - If you also want audit-log or other admin-territory Graph endpoints,
     add scopes like `AuditLog.Read.All` here explicitly and consent them.
     App-only mode gets exactly what's admin-consented on this registration —
     nothing more, nothing tied to who (if anyone) is signed in. At tiers 1-2
     the equivalent is whatever delegated scope the app you signed in
     through (the Azure CLI's own app, or your tier-2 registration) is
     itself consented for — your Global Admin role does not add scopes that
     app was never granted; it only matters within whatever the app already
     has.
3. Set the env vars:

   ```powershell
   setx MS_ADMIN_TENANT_ID "<tenant id>"
   setx MS_ADMIN_CLIENT_ID "<app id>"
   setx MS_ADMIN_CLIENT_SECRET "<secret>"
   ```

   With all three set, this tier always wins the chain — it's tried first,
   before `cli` or `device` — so setting these doesn't require unsetting
   anything from tier 1/2.
4. **Leave `MCP_MS_ALLOW_WRITES` unset.** Every server stays read-only until
   you set it to exactly `1` — and even then each destructive call needs
   `confirm: true`. Set it per-session when you mean it, not globally.

Force a specific tier regardless of what else is configured with
`MS_ADMIN_AUTH=secret|cli|device` (see the README's admin auth chain table);
leave it unset for the automatic secret → cli → device fallback used above.

### 3e. Verify each server before trusting it

```bash
mcp-msgraph doctor      # or: npx -y @badali404/mcp-msgraph@latest doctor
mcp-o365-user doctor
```

Doctor proves auth end-to-end and prints which chain link authenticated,
whether the token is app-only or delegated, and the scopes/roles actually
granted. A server that starts is not a server that authenticates.

---

## 4. Optional: crew's new switches

- **Global crew config** — create `~/.claude/crew/config.json` by hand with
  just the keys you want machine-wide (e.g. your QA provider); every crew
  repo's own `.crew/config.json` still wins where both set a key. No command
  creates it — that is deliberate.
- **Obsidian Kanban tickets** in a repo: set `tracker: "obsidian"` plus the
  `obsidian` block in that repo's `.crew/config.json`, or answer the tracker
  question in `/crew:init`. Board and ticket notes live in
  `<vault>/Boards/<repo>/`.
- **Graph export into the codegraphs vault**: in a crew repo, set
  `graph.obsidian.dir` to `C:\repos\claude-memories-codegraphs\<org>` and
  `graph.obsidian.layout` to `"org/repo"`. Export still asks for in-session
  consent (`graph.obsidian.confirmed`) every setup.

---

## Done-when checklist

- [ ] `/obsidian-vault:doctor` reports all vaults green, vault has a real
      `.git` with a remote, CLAUDE.md matches reality
- [ ] Gardener scheduled; a fresh log appears tomorrow
- [ ] `npm view @badali404/mcp-ms-core version` returns a version
- [ ] `npx -y @badali404/mcp-msgraph@latest doctor` authenticates (reports
      which tier/link authenticated — `cli` is fine, no app registration
      required for it)
- [ ] `mcp-o365-user` device-code sign-in completes; a calendar read works
- [ ] `MCP_MS_ALLOW_WRITES` is **not** set anywhere persistent
