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

## 3. Entra app registrations and credentials for the MCP servers

Two app registrations — the user/admin split is structural, so they must stay
separate apps.

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

### 3b. Admin-scope app (for `mcp-msgraph`, `mcp-intune`, `mcp-o365-admin`)

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
3. Set the env vars:

   ```powershell
   setx MS_ADMIN_TENANT_ID "<tenant id>"
   setx MS_ADMIN_CLIENT_ID "<app id>"
   setx MS_ADMIN_CLIENT_SECRET "<secret>"
   ```

4. **Leave `MCP_MS_ALLOW_WRITES` unset.** Every server stays read-only until
   you set it to exactly `1` — and even then each destructive call needs
   `confirm: true`. Set it per-session when you mean it, not globally.

### 3c. Verify each server before trusting it

```bash
mcp-msgraph doctor      # or: npx -y @badali404/mcp-msgraph@latest doctor
mcp-o365-user doctor
```

Doctor proves auth end-to-end and prints the scopes actually granted.
A server that starts is not a server that authenticates.

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
- [ ] `npx -y @badali404/mcp-msgraph@latest doctor` authenticates
- [ ] `mcp-o365-user` device-code sign-in completes; a calendar read works
- [ ] `MCP_MS_ALLOW_WRITES` is **not** set anywhere persistent
