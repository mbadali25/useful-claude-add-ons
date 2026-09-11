#!/usr/bin/env bash
#
# bootstrap.sh - install Nuclei plus the eight other gizmoduck scanners on
# Linux / WSL Ubuntu 24.04.
#
# Each tool installs independently: a failure in one does not stop the rest
# (THDDEV multi-scanner routine work, 2026-09-10 plan Task 20). The ONE
# exception is the Nuclei template download, which still aborts the script -
# see update_nuclei_templates() below for why.
#
# Usage:  ./bootstrap.sh
#
set -uo pipefail   # deliberately no -e: try_install isolates failures itself

FAILED=()

# Runs $2.. as a function, in a subshell with its own `set -e` so a failing
# command inside it aborts just that one install instead of the whole script.
# The subshell's exit status is what the `if` below tests, so -e in the
# *parent* shell (which we don't set) never comes into play.
try_install() {
  local name="$1"; shift
  echo ">> installing ${name}..."
  if ( set -e; "$@" ); then
    echo ">> ${name}: OK"
  else
    echo "!! ${name}: install failed - continuing with the rest" >&2
    FAILED+=("$name")
  fi
}

install_prereqs() {
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y curl unzip git python3 python3-pip wkhtmltopdf
  fi
}

install_nuclei() {
  local arch
  case "$(uname -m)" in
    x86_64|amd64) arch=amd64 ;;
    aarch64|arm64) arch=arm64 ;;
    *) echo "Unsupported arch $(uname -m)"; return 1 ;;
  esac

  local ver
  ver=$(curl -fsSL https://api.github.com/repos/projectdiscovery/nuclei/releases/latest \
        | grep '"tag_name"' | head -1 | cut -d'"' -f4)
  if [[ -z "$ver" ]]; then
    echo "Could not determine latest Nuclei version"
    return 1
  fi
  local num="${ver#v}"
  local zip="nuclei_${num}_linux_${arch}.zip"

  local tmp
  tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/$zip" \
    "https://github.com/projectdiscovery/nuclei/releases/download/${ver}/${zip}"
  unzip -oq "$tmp/$zip" -d "$tmp"
  sudo mv "$tmp/nuclei" /usr/local/bin/nuclei
  sudo chmod +x /usr/local/bin/nuclei
  rm -rf "$tmp"

  echo ">> installed: $(nuclei -version 2>&1 | head -1)"
}

update_nuclei_templates() {
  # NOT run through try_install, and this is deliberate - do not "fix" it into
  # a soft-fail like the others below. A template-less Nuclei still runs and
  # still exits 0, but silently finds nothing on every target, which is a
  # worse outcome than a loud bootstrap failure the operator actually sees.
  echo ">> downloading Nuclei community templates..."
  if ! nuclei -update-templates -silent; then
    echo "!! template download failed. The engine is installed but has no" >&2
    echo "!! templates, so a scan would report zero findings on every target." >&2
    echo "!! Re-run 'nuclei -update-templates' once the network allows it." >&2
    exit 1
  fi
}

install_nmap() {
  sudo apt-get install -y nmap
}

install_nikto() {
  sudo apt-get install -y nikto
}

install_testssl() {
  local dir=/opt/testssl.sh
  if [[ -d "$dir/.git" ]]; then
    sudo git -C "$dir" pull --ff-only
  else
    sudo rm -rf "$dir"
    sudo git clone --depth 1 https://github.com/drwetter/testssl.sh.git "$dir"
  fi
  sudo chmod +x "$dir/testssl.sh"
  sudo ln -sf "$dir/testssl.sh" /usr/local/bin/testssl.sh
}

install_trivy() {
  # Official install script (documented at trivy.dev) - resolves the latest
  # release and puts the binary on the given path itself.
  curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \
    | sudo sh -s -- -b /usr/local/bin
}

install_checkov() {
  pip3 install --user --upgrade checkov
}

install_depcheck() {
  local ver
  ver=$(curl -fsSL https://api.github.com/repos/jeremylong/DependencyCheck/releases/latest \
        | grep '"tag_name"' | head -1 | cut -d'"' -f4)
  if [[ -z "$ver" ]]; then
    echo "Could not determine latest Dependency-Check version"
    return 1
  fi
  local num="${ver#v}"
  local zip="dependency-check-${num}-release.zip"

  local tmp
  tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/$zip" \
    "https://github.com/jeremylong/DependencyCheck/releases/download/${ver}/${zip}"
  sudo unzip -oq "$tmp/$zip" -d /opt
  rm -rf "$tmp"
  sudo chmod +x /opt/dependency-check/bin/dependency-check.sh
  sudo ln -sf /opt/dependency-check/bin/dependency-check.sh /usr/local/bin/dependency-check

  # Dependency-Check is a Java app; make sure something can run it.
  command -v java >/dev/null 2>&1 || sudo apt-get install -y default-jre
}

install_sqlmap() {
  # git clone is sqlmap's own documented install method - there is no PyPI
  # package (spec 13.9: no --report-json either, but that's a routine.py
  # adapter concern, not a bootstrap one).
  local dir=/opt/sqlmap
  if [[ -d "$dir/.git" ]]; then
    sudo git -C "$dir" pull --ff-only
  else
    sudo rm -rf "$dir"
    sudo git clone --depth 1 https://github.com/sqlmapproject/sqlmap.git "$dir"
  fi
  sudo tee /usr/local/bin/sqlmap >/dev/null <<'EOS'
#!/usr/bin/env bash
exec python3 /opt/sqlmap/sqlmap.py "$@"
EOS
  sudo chmod +x /usr/local/bin/sqlmap
}

install_zap() {
  # ZAP 2.16+ requires Java 17 minimum (spec 13.3). A missing or too-old JRE
  # lets this install step "succeed" while ZAP itself refuses to start later -
  # which looks like a missing tool for reasons nobody can see from `doctor`.
  # Check for 17+ before doing anything else, matching the JRE gate ZAP needs.
  if ! java -version 2>&1 | grep -qE '"(1\.)?(1[7-9]|[2-9][0-9])'; then
    sudo apt-get install -y openjdk-17-jre
  fi

  # The Crossplatform zip ships both zap.sh and zap.bat plus the Automation
  # Framework add-on, so the same download works for bootstrap.ps1 too. This
  # is a plain unzip, not the docker `zaproxy/zap-stable` image - Docker is
  # not installed on the operator machine and using it here was explicitly
  # ruled out (do not "fix" this back to a docker run).
  local ver
  ver=$(curl -fsSL https://api.github.com/repos/zaproxy/zaproxy/releases/latest \
        | grep '"tag_name"' | head -1 | cut -d'"' -f4)
  if [[ -z "$ver" ]]; then
    echo "Could not determine latest ZAP version"
    return 1
  fi
  local num="${ver#v}"
  local zip="ZAP_${num}_Crossplatform.zip"

  local tmp
  tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/$zip" \
    "https://github.com/zaproxy/zaproxy/releases/download/${ver}/${zip}"
  sudo unzip -oq "$tmp/$zip" -d /opt
  rm -rf "$tmp"
  sudo chmod +x "/opt/ZAP_${num}/zap.sh"
  sudo ln -sf "/opt/ZAP_${num}/zap.sh" /usr/local/bin/zap.sh
}

try_install "prerequisites"      install_prereqs
try_install "nuclei"             install_nuclei
update_nuclei_templates          # hard-fail exception - see comment above, do not wrap in try_install
try_install "nmap"               install_nmap
try_install "nikto"              install_nikto
try_install "testssl.sh"         install_testssl
try_install "trivy"              install_trivy
try_install "checkov"            install_checkov
try_install "dependency-check"   install_depcheck

# dependency-check's first run downloads the entire NVD CVE corpus. Without an
# API key, NIST rate-limits that sync to ~5 requests/30s - on a fresh machine
# that first run can take the better part of an hour and gives no progress
# output, which looks exactly like a hang. An API key raises the limit to
# ~50/30s (~10x). Print this unconditionally (not just on install success):
# it matters just as much if dependency-check gets installed by hand later.
# Non-interactive on purpose - do not prompt for the key here.
cat <<'NVDMSG'

------------------------------------------------------------
 Dependency-Check + NVD API key (optional, recommended):
 The first scan syncs the full NVD CVE database. Without an API
 key NIST rate-limits that to ~5 req/30s (~10x slower than with
 one) - the run can take a long time and print nothing, which
 looks hung but isn't.

 Get a free key (no account, no cost - just an email + org):
   https://nvd.nist.gov/developers/request-an-api-key
 NIST emails an ACTIVATION LINK, not the key itself - open that
 link, then copy the key shown on the page behind it.

 Then set it before running dependency-check:
   export NVD_API_KEY=<your key>
------------------------------------------------------------
NVDMSG

try_install "sqlmap"             install_sqlmap
try_install "OWASP ZAP"          install_zap

echo
if [[ ${#FAILED[@]} -gt 0 ]]; then
  echo "!! ${#FAILED[@]} tool(s) failed to install: ${FAILED[*]}" >&2
  echo "!! Re-run this script, or install them by hand, then check with:" >&2
  echo "!!   /gizmoduck:doctor" >&2
  echo "!! If a failure looks like your AV/EDR deleted or quarantined a file (nikto," >&2
  echo "!! sqlmap, ZAP, a Nuclei template), see docs/antivirus-exclusions.md." >&2
else
  echo ">> all tools installed."
fi

cat <<'MSG'

------------------------------------------------------------
 Nuclei is ready. Try:
   nuclei -u https://example.com -severity critical,high

 Or drive it through the plugin:
   /gizmoduck:scan https://your-new-site.com high

 For the full nine-tool routine across a manifest of targets:
   /gizmoduck:doctor    (confirm what actually installed)
------------------------------------------------------------
MSG
