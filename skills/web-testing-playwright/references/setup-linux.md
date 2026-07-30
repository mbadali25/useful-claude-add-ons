# Installing Playwright on Linux

Run `scripts/check_env.py` first, show the user what's missing, and get consent before
installing — the system-library step needs sudo and the browser download is a few hundred
megabytes.

## Contents
- [The short version](#the-short-version)
- [Getting Python or Node](#getting-python-or-node)
- [The externally-managed-environment error](#the-externally-managed-environment-error)
- [System libraries](#system-libraries-the-linux-specific-part)
- [Headless servers and headed mode](#headless-servers-and-headed-mode)
- [Docker](#docker)
- [CI](#ci)
- [Environment variables](#environment-variables)

## The short version

```bash
python3 -m pip install playwright
python3 -m playwright install --with-deps chromium   # prompts for sudo
```

`--with-deps` combines the browser download and the system-package install. Without root,
split it:

```bash
python3 -m playwright install chromium            # no root needed
sudo python3 -m playwright install-deps chromium  # root needed
```

Node equivalent:
```bash
npm init playwright@latest        # new project, scaffolds tests + config
npx playwright install --with-deps chromium
```

## Getting Python or Node

Python 3 is present on essentially every modern distro. If `pip` is missing:

| Distro | Command |
|---|---|
| Debian/Ubuntu | `sudo apt-get update && sudo apt-get install -y python3-pip` |
| Fedora/RHEL | `sudo dnf install -y python3-pip` |
| Arch | `sudo pacman -S python-pip` |
| Alpine | `sudo apk add python3 py3-pip` |

For Node, distro packages are often years out of date. Prefer nvm (no root, easy version
switching):

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc
nvm install --lts
```

Or NodeSource for a system-wide install. Tell the user which you're doing and why before
piping a remote script into bash.

Note that **Alpine/musl is not supported** by Playwright's prebuilt browsers. On Alpine,
use the official Docker image or a glibc-based distro instead of fighting it.

## The `externally-managed-environment` error

On Debian 12, Ubuntu 23.04+, and Fedora 38+, `pip install` into the system Python is
blocked by PEP 668. Three ways out, best first:

```bash
# 1. Virtual environment — cleanest, no root, no interference with system packages
python3 -m venv .venv && source .venv/bin/activate && pip install playwright

# 2. User install
python3 -m pip install --user playwright

# 3. Override the guard — fine in a throwaway container, not on the user's daily machine
python3 -m pip install --break-system-packages playwright
```

If you create a venv, every later command must use it. Either keep it activated or call
`.venv/bin/python3 scripts/audit_page.py ...` explicitly — a script silently run by the
system Python will report Playwright as missing and cause confusion.

## System libraries (the Linux-specific part)

Chromium needs a couple dozen shared libraries that a server image usually lacks. The
symptom is a launch failure listing missing `.so` files:

```
error while loading shared libraries: libnss3.so: cannot open shared object file
```

Fix:
```bash
sudo python3 -m playwright install-deps chromium    # or: npx playwright install-deps
```

Let Playwright pick the packages rather than hand-listing them — the set differs by distro
and by Playwright version. If `install-deps` doesn't support the distro (it knows Debian,
Ubuntu, and recent Fedora/RHEL), the missing libraries have to be installed by hand from
the error output; on Arch the usual set is `nss nspr atk at-spi2-atk cups libdrm libxkbcommon
at-spi2-core libxcomposite libxdamage libxfixes libxrandr mesa pango cairo alsa-lib`.

## Headless servers and headed mode

**Headless needs no display at all.** No X, no Wayland, no xvfb. If a headless run fails,
the cause is missing libraries, not a missing display — don't send the user down the xvfb
path for that.

For headed mode on a box with no display:

```bash
sudo apt-get install -y xvfb
xvfb-run -a python3 scripts/audit_page.py https://example.com --headed
```

Often the better answer is to skip headed mode entirely and record evidence instead:

```python
context = browser.new_context(record_video_dir="videos/")
context.tracing.start(screenshots=True, snapshots=True, sources=True)
# ... the run ...
context.tracing.stop(path="trace.zip")
```

Then `playwright show-trace trace.zip` on a machine that does have a display — the trace
viewer gives you DOM snapshots at every step, which is more useful than watching it live.

WSL2 on Windows 11 has WSLg, so headed mode works with no setup. On Windows 10, stick to
headless.

## Docker

The official image has browsers and every system dependency preinstalled, which sidesteps
this whole section:

```bash
docker run --rm -it -v "$(pwd)":/work -w /work \
  mcr.microsoft.com/playwright/python:v1.56.0-jammy \
  python3 scripts/audit_page.py https://example.com --out /work/audit
```

Match the image tag to the installed Playwright version — a mismatch produces an
"executable doesn't exist" error, because Playwright looks for a browser build revision
the image doesn't carry. The Node image is `mcr.microsoft.com/playwright:v1.56.0-jammy`.

Two container gotchas:

- Chromium's sandbox needs either `--cap-add=SYS_ADMIN` or a seccomp profile. The official
  images handle this. In a hand-rolled container you may need `--no-sandbox`, which
  weakens isolation — acceptable for testing your own app, not for browsing untrusted
  pages.
- Default `/dev/shm` is 64 MB and Chromium will crash on heavy pages. Add `--shm-size=1g`.

## CI

```yaml
- run: pip install playwright
- run: python -m playwright install --with-deps chromium
```

Cache `~/.cache/ms-playwright` keyed on the Playwright version to skip the re-download on
every run. Pin the Playwright version in requirements so browser revisions don't shift
under you mid-sprint.

## Environment variables

```bash
export APP_USER='someone@example.com'
export APP_PASSWORD='...'
```

Prefix the command with a space (`  export ...`) if `HISTCONTROL=ignorespace` is set, or
better, keep secrets in a gitignored `.env` and source it. Never commit `.env` or the
`auth.json` produced by `login.py`.

Useful Playwright variables:

| Variable | Effect |
|---|---|
| `PLAYWRIGHT_BROWSERS_PATH` | Where browsers are stored; `0` puts them in the package dir |
| `PWDEBUG=1` | Opens the Inspector, runs headed, disables timeouts |
| `DEBUG=pw:api` | Logs every Playwright call — good for "it hangs and I don't know where" |
| `DEBUG=pw:browser` | Browser process stdout/stderr, for launch failures |
| `PLAYWRIGHT_DOWNLOAD_HOST` | Internal mirror for the browser download |
