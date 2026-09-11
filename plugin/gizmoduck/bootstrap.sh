#!/usr/bin/env bash
#
# bootstrap.sh - install Nuclei + templates on Linux / WSL Ubuntu 24.04.
# Downloads the prebuilt binary (no Go needed) and updates templates.
#
# Usage:  ./bootstrap.sh
#
set -euo pipefail

echo ">> installing prerequisites (curl, unzip)..."
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y && sudo apt-get install -y curl unzip python3 wkhtmltopdf
fi

# arch
case "$(uname -m)" in
  x86_64|amd64) ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) echo "Unsupported arch $(uname -m)"; exit 1 ;;
esac

echo ">> finding latest Nuclei release..."
VER=$(curl -fsSL https://api.github.com/repos/projectdiscovery/nuclei/releases/latest \
      | grep '"tag_name"' | head -1 | cut -d'"' -f4)
[[ -z "$VER" ]] && { echo "Could not determine latest version"; exit 1; }
NUM="${VER#v}"
ZIP="nuclei_${NUM}_linux_${ARCH}.zip"

echo ">> downloading $ZIP ..."
TMP="$(mktemp -d)"
curl -fsSL -o "$TMP/$ZIP" \
  "https://github.com/projectdiscovery/nuclei/releases/download/${VER}/${ZIP}"
unzip -oq "$TMP/$ZIP" -d "$TMP"
sudo mv "$TMP/nuclei" /usr/local/bin/nuclei
sudo chmod +x /usr/local/bin/nuclei
rm -rf "$TMP"

echo ">> installed: $(nuclei -version 2>&1 | head -1)"
echo ">> downloading community templates..."
# Not `|| true`. Nuclei with no templates finds nothing and exits 0, which is
# indistinguishable from a clean scan - so a bootstrap that swallows this
# leaves behind a scanner that reports every target as healthy.
if ! nuclei -update-templates -silent; then
  echo "!! template download failed. The engine is installed but has no" >&2
  echo "!! templates, so a scan would report zero findings on every target." >&2
  echo "!! Re-run 'nuclei -update-templates' once the network allows it." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# The rest of the scanner suite.
#
# Nuclei is a known-issue template scanner. On its own it finds almost nothing
# on an authenticated app behind a WAF - a real sweep of 18 such endpoints
# returned 294 findings, every one of them Info-severity fingerprinting. These
# cover what it structurally cannot: TLS configuration, dependency CVEs,
# committed secrets, IaC misconfiguration, and source-level flaws such as a
# missing authorization check.
#
# Failures here are reported, not fatal: an incomplete suite is still better
# than no scanner, and `gizmoduck.py doctor` names exactly what is missing.
# ---------------------------------------------------------------------------
echo ""
echo ">> installing the scanner suite..."

if ! command -v trivy >/dev/null 2>&1; then
  echo ">> trivy (dependency CVEs, committed secrets, Terraform misconfiguration)"
  if command -v brew >/dev/null 2>&1; then
    brew install trivy || echo "!! trivy install failed - install it by hand"
  elif command -v apt-get >/dev/null 2>&1; then
    # /usr/local/bin, matching where this script already puts nuclei above.
    curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \
      | sudo sh -s -- -b /usr/local/bin || echo "!! trivy install failed - install it by hand"
  else
    echo "!! no brew or apt-get; install trivy by hand: https://aquasecurity.github.io/trivy"
  fi
fi

# sslyze and semgrep are Python tools. --user so they land on PATH for the
# account running scans rather than inside whatever virtualenv is active now.
if command -v python3 >/dev/null 2>&1; then
  for pkg in sslyze semgrep; do
    if ! command -v "$pkg" >/dev/null 2>&1; then
      echo ">> $pkg"
      python3 -m pip install --user --quiet "$pkg" \
        || echo "!! $pkg install failed - install it by hand"
    fi
  done
else
  echo "!! python3 not found; sslyze and semgrep not installed"
fi

cat <<'MSG'

>> optional, not installed by default:
   OWASP ZAP  - authenticated crawler-driven DAST. Minutes per target.
                Install, then scan with --with-zap.
   checkov    - more IaC checks than trivy, but checkov OSS returns no
                severity, so its findings are floored at Low and will not
                appear in a Medium-and-above report. Scan with --with-checkov.

------------------------------------------------------------
 Run 'gizmoduck.py doctor' to confirm every tool resolved.
 Then:
   /gizmoduck:scan https://your-new-site.com

 Add --source <dir> so trivy and semgrep have a tree to read;
 without it they report as SKIPPED, not clean.
------------------------------------------------------------
MSG
