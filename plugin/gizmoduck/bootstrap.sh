#!/usr/bin/env bash
#
# bootstrap.sh - install Nuclei plus the eight other gizmoduck scanners on
# Linux / WSL Ubuntu 24.04.
#
# Each tool installs independently: a failure in one does not stop the rest
# (ACME multi-scanner routine work, 2026-09-10 plan Task 20). The ONE
# exception is the Nuclei template download, which still aborts the script -
# see update_nuclei_templates() below for why.
#
# Usage:  ./bootstrap.sh
#
set -uo pipefail   # deliberately no -e: try_install isolates failures itself

FAILED=()

# Install locations. The defaults are the real ones; the test suite points
# them at a throwaway directory so it can run the real download / verify /
# unpack steps without touching the machine. These are a TEST seam, not a
# supported setting: everything under them is written with `sudo rm -rf` /
# `sudo mv`, so a GIZMODUCK_*_DIR inherited from a profile or a CI job must
# not redirect a real run. They are honoured only with
# GIZMODUCK_BOOTSTRAP_TEST=1, and otherwise ignored with a notice (C-0015).
BIN_DIR=/usr/local/bin
OPT_DIR=/opt
APT_LISTS_DIR=/var/lib/apt/lists
if [[ "${GIZMODUCK_BOOTSTRAP_TEST:-}" == 1 ]]; then
  BIN_DIR="${GIZMODUCK_BIN_DIR:-$BIN_DIR}"
  OPT_DIR="${GIZMODUCK_OPT_DIR:-$OPT_DIR}"
  APT_LISTS_DIR="${GIZMODUCK_APT_LISTS_DIR:-$APT_LISTS_DIR}"
elif [[ -n "${GIZMODUCK_BIN_DIR:-}${GIZMODUCK_OPT_DIR:-}${GIZMODUCK_APT_LISTS_DIR:-}" ]]; then
  echo "!! GIZMODUCK_BIN_DIR / GIZMODUCK_OPT_DIR / GIZMODUCK_APT_LISTS_DIR are test-only and" >&2
  echo "!!   ignored here (they need GIZMODUCK_BOOTSTRAP_TEST=1); installing to the defaults." >&2
fi

# Time limits, so a stalled network fails one step instead of hanging the
# whole bootstrap (and a cloud session's setup phase with it). API calls are
# small; downloads include ZAP's ~286MB zip, hence the long ceiling.
CURL_API=(--connect-timeout 20 --max-time 60)
CURL_DL=(--connect-timeout 20 --max-time 1800)

# Runs git with a low-speed abort (under 1000 B/s for 30s) and, where
# coreutils' `timeout` exists, a hard ceiling of $1 seconds. Without `timeout`
# it still runs, with only the low-speed abort.
git_net() {
  local secs="$1"; shift
  if command -v timeout >/dev/null 2>&1; then
    GIT_HTTP_LOW_SPEED_LIMIT=1000 GIT_HTTP_LOW_SPEED_TIME=30 timeout "$secs" git "$@"
  else
    GIT_HTTP_LOW_SPEED_LIMIT=1000 GIT_HTTP_LOW_SPEED_TIME=30 git "$@"
  fi
}

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

# Prints the newest stable release tag (e.g. v3.11.1) of GitHub repo $1
# (owner/repo) on stdout; $2 is the tool name for messages.
#
# The REST API (releases/latest) is tried first, as before. Some networks -
# the Claude Code cloud sandbox among them - answer api.github.com with a 403
# while still serving git and the versioned releases/download/<tag>/ assets,
# so on an API failure this falls back to `git ls-remote --tags`. Only plain
# X.Y.Z (optionally v-prefixed) tags count there: rc/beta/alpha/pre tags,
# ZAP's w2026-... weekly tags and oddities like nuclei's `v.1.0.0` are
# skipped, and the highest by version order wins. A tag is not proof a
# release with assets exists, but the download that follows fails loudly if
# it doesn't. When both lookups fail it says so naming the tool and returns
# 1, leaving try_install's isolation to carry on with the rest.
resolve_latest_tag() {
  local repo="$1" tool="$2" ver=""
  ver=$(curl -fsSL "${CURL_API[@]}" "https://api.github.com/repos/${repo}/releases/latest" 2>/dev/null \
        | grep '"tag_name"' | head -1 | cut -d'"' -f4) || ver=""
  if [[ -n "$ver" ]]; then
    printf '%s\n' "$ver"
    return 0
  fi
  echo ">> ${tool}: GitHub API lookup failed - trying git tags of github.com/${repo}" >&2
  ver=$(git_net 120 ls-remote --tags --refs "https://github.com/${repo}.git" 2>/dev/null \
        | sed -n 's#^.*refs/tags/##p' \
        | grep -E '^v?[0-9]+\.[0-9]+\.[0-9]+$' \
        | awk '{ n = $0; sub(/^v/, "", n); print n, $0 }' \
        | sort -V -k1,1 | tail -1 | cut -d' ' -f2) || ver=""
  if [[ -n "$ver" ]]; then
    printf '%s\n' "$ver"
    return 0
  fi
  echo "!! ${tool}: could not determine the latest version - both the GitHub API" >&2
  echo "!!   (api.github.com/repos/${repo}/releases/latest) and" >&2
  echo "!!   'git ls-remote --tags https://github.com/${repo}.git' failed or found no stable tag." >&2
  return 1
}

# Idempotency: a tool that is on PATH AND passes a probe is reported and
# skipped, so re-running this script (or a cloud session's setup script
# running it on every start) does not re-download hundreds of MB. The probe
# is `<cmd> --version` unless $3 names a function to call with the path
# instead; existence alone is not trusted, so a zero-byte binary or a
# half-unpacked install fails the probe and is reinstalled. Set
# GIZMODUCK_BOOTSTRAP_FORCE=1 to reinstall/upgrade everything anyway.
already_installed() {
  local name="$1" cmd="$2" probe="${3:-}" path
  [[ "${GIZMODUCK_BOOTSTRAP_FORCE:-}" == 1 ]] && return 1
  path=$(command -v "$cmd" 2>/dev/null) || return 1
  # An empty file with +x "runs" (bash treats it as an empty script, exit 0),
  # so a zero-byte leftover would pass any probe - check size first.
  if [[ ! -s "$path" ]]; then
    echo ">> ${name}: ${path} is empty - reinstalling"; return 1
  fi
  if [[ -n "$probe" ]]; then
    "$probe" "$path" >/dev/null 2>&1 || {
      echo ">> ${name}: ${path} is present but fails its check - reinstalling"; return 1; }
  else
    "$path" --version >/dev/null 2>&1 || {
      echo ">> ${name}: ${path} is present but '--version' fails - reinstalling"; return 1; }
  fi
  echo ">> ${name}: already installed (${path}) - skipping; GIZMODUCK_BOOTSTRAP_FORCE=1 reinstalls"
  return 0
}

# Checks $2, a file in directory $1, against its line in checksums file $3
# (same directory, `sha256sum` format). The line is matched on its exact file
# name field, so foo.zip never picks up foo.zip.sig's hash. No line, or a
# mismatch, refuses: nothing unverified gets installed.
verify_sha256() {
  local dir="$1" file="$2" sums="$3" want got
  want=$(awk -v f="$file" '$2 == f || $2 == "*" f { print $1; exit }' "$dir/$sums" 2>/dev/null)
  if [[ -z "$want" ]]; then
    echo "!! ${file}: no checksum line in ${sums} - refusing to install it" >&2
    return 1
  fi
  got=$(sha256sum "$dir/$file" | cut -d' ' -f1)
  if [[ "$want" != "$got" ]]; then
    echo "!! ${file}: sha256 mismatch (expected ${want}, got ${got}) - refusing to install it" >&2
    return 1
  fi
  echo ">> ${file}: sha256 OK"
}

# Every apt-get call goes through these two. The options:
#  - APT::Sandbox::User=root: apt drops to its `_apt` user to fetch and verify
#    indexes, writing temp files under /tmp. Some images (the Claude Code cloud
#    image was measured with /tmp at 755 root:root) leave `_apt` unable to, and
#    apt-get update/install fail with "Couldn't create temporary file
#    /tmp/apt.conf.XXXX". Running the sandbox as root sidesteps that without
#    touching /tmp's permissions - do not "fix" this with a chmod of /tmp.
#  - DPkg::Lock::Timeout=600: wait for another apt/dpkg holding the lock (an
#    unattended-upgrades run, or a parallel setup step) instead of failing.
# apt_install also runs `apt-get clean`, since disk can be a fixed allowance
# and the downloaded .debs are dead weight once installed.
apt_get() {
  sudo apt-get -o APT::Sandbox::User=root -o DPkg::Lock::Timeout=600 "$@"
}

apt_lists_present() {
  compgen -G "${APT_LISTS_DIR}/*_Packages*" >/dev/null
}

apt_install() {
  # Package lists can be empty (a fresh image, or one that just ran `clean`
  # and a lists purge); install would then fail with "Unable to locate
  # package", so refresh them first. Each tool installs in its own subshell,
  # so a flag would not survive between them - the lists themselves are the
  # record.
  apt_lists_present || apt_get update -y || return
  # Explicit `|| return`: a caller like `cmd || apt_install x` runs this with
  # set -e suspended, and a failed install must not be masked by a clean that
  # succeeds. A failed clean only costs disk, so it warns and moves on.
  apt_get install -y "$@" || return
  apt_get clean || echo "!! apt-get clean failed - continuing" >&2
}

install_prereqs() {
  local missing=0 c
  for c in curl unzip git python3 pip3 wkhtmltopdf; do
    command -v "$c" >/dev/null 2>&1 || missing=1
  done
  if [[ $missing == 0 && "${GIZMODUCK_BOOTSTRAP_FORCE:-}" != 1 ]]; then
    echo ">> prerequisites: already installed - skipping apt-get"
    return 0
  fi
  if command -v apt-get >/dev/null 2>&1; then
    apt_get update -y
    apt_install curl unzip git python3 python3-pip wkhtmltopdf
  fi
}

install_nuclei() {
  already_installed nuclei nuclei probe_nuclei && return 0
  local arch
  case "$(uname -m)" in
    x86_64|amd64) arch=amd64 ;;
    aarch64|arm64) arch=arm64 ;;
    *) echo "Unsupported arch $(uname -m)"; return 1 ;;
  esac

  local ver
  ver=$(resolve_latest_tag projectdiscovery/nuclei "nuclei") || return 1
  local num="${ver#v}"
  local zip="nuclei_${num}_linux_${arch}.zip" sums="nuclei_${num}_checksums.txt"
  local base="https://github.com/projectdiscovery/nuclei/releases/download/${ver}"

  # Stage under /opt (where the rest of gizmoduck's manually-installed tools
  # already live) instead of /tmp - /tmp is world-writable and the most
  # common malware drop location on Linux too, so a security tool's own
  # download shouldn't sit there even briefly. Nuclei's only permanent home
  # is the single /usr/local/bin/nuclei binary, so this staging dir is
  # scratch space, not a destination - remove it once the binary is moved.
  local stage="${OPT_DIR}/gizmoduck-nuclei-download"
  sudo rm -rf "$stage"
  sudo mkdir -p "$stage"
  sudo curl -fsSL "${CURL_DL[@]}" -o "$stage/$zip" "$base/$zip"
  sudo curl -fsSL "${CURL_API[@]}" -o "$stage/$sums" "$base/$sums"
  verify_sha256 "$stage" "$zip" "$sums" || { sudo rm -rf "$stage"; return 1; }
  sudo unzip -oq "$stage/$zip" -d "$stage"
  sudo mv "$stage/nuclei" "${BIN_DIR}/nuclei"
  sudo chmod +x "${BIN_DIR}/nuclei"
  sudo rm -rf "$stage"

  echo ">> installed: $("${BIN_DIR}/nuclei" -version 2>&1 | head -1)"
}

probe_nuclei() { "$1" -version; }

update_nuclei_templates() {
  # NOT run through try_install, and this is deliberate - do not "fix" it into
  # a soft-fail like the others below. A template-less Nuclei still runs and
  # still exits 0, but silently finds nothing on every target, which is a
  # worse outcome than a loud bootstrap failure the operator actually sees.
  #
  # Success is judged by templates actually being on disk, not by the exit
  # code: where api.github.com is refused, `nuclei -update-templates` exits 0
  # having downloaded nothing (measured in the Claude Code cloud sandbox with
  # nuclei v3.11.1 - an empty ~/nuclei-templates and rc 0). Only when NO
  # templates are on disk is the same release cloned with git, which those
  # networks still allow. A failed update over existing templates keeps them.
  if ! command -v nuclei >/dev/null 2>&1; then
    echo "!! the nuclei engine is not installed, so there is nothing to fetch" >&2
    echo "!! templates for. Fix the nuclei install above and re-run." >&2
    exit 1
  fi
  echo ">> downloading Nuclei community templates..."
  local tdir rc=0
  tdir=$(nuclei_templates_dir)
  nuclei -update-templates -silent || rc=$?
  if nuclei_templates_present "$tdir"; then
    if [[ $rc -ne 0 ]]; then
      echo "!! nuclei -update-templates failed (exit ${rc}); keeping the existing templates in ${tdir}" >&2
    fi
    return 0
  fi
  echo ">> no templates in ${tdir} after nuclei -update-templates (exit ${rc}) - trying git clone" >&2
  if clone_nuclei_templates "$tdir" && nuclei_templates_present "$tdir"; then
    echo ">> nuclei templates cloned to ${tdir}"
    return 0
  fi
  echo "!! template download failed. The engine is installed but has no" >&2
  echo "!! templates, so a scan would report zero findings on every target." >&2
  echo "!! Re-run 'nuclei -update-templates' once the network allows it." >&2
  exit 1
}

# Where nuclei keeps its community templates: the directory its own config
# records, else its default ~/nuclei-templates.
nuclei_templates_dir() {
  local d=""
  d=$(python3 -c 'import json, os
p = os.path.expanduser("~/.config/nuclei/.templates-config.json")
print(json.load(open(p)).get("nuclei-templates-directory", ""))' 2>/dev/null) || d=""
  printf '%s\n' "${d:-$HOME/nuclei-templates}"
}

nuclei_templates_present() {
  [[ -n "$(find "$1" -name '*.yaml' -print -quit 2>/dev/null)" ]]
}

# Clones the newest stable nuclei-templates release and moves it to $1 -
# but only if $1 is missing or holds no files at all. The path comes from a
# user-editable config, so this never deletes anything that is a file: the
# clone goes into a sibling temp dir first, only empty directories in $1 are
# removed, and if any file remains the clone is discarded and $1 is left as
# it was.
clone_nuclei_templates() {
  local tdir="$1" tag tmp
  tag=$(resolve_latest_tag projectdiscovery/nuclei-templates "nuclei templates") || return 1
  mkdir -p "$(dirname "$tdir")" || return 1
  tmp=$(mktemp -d "${tdir%/}.gizmoduck-clone.XXXXXX") || return 1
  if ! git_net 900 -c advice.detachedHead=false clone -q --depth 1 --branch "$tag" \
      https://github.com/projectdiscovery/nuclei-templates.git "$tmp/t"; then
    rm -rf "$tmp"   # our own temp dir, never the user's
    return 1
  fi
  if [[ -e "$tdir" ]]; then
    find "$tdir" -depth -type d -empty -delete 2>/dev/null
    if [[ -e "$tdir" ]]; then
      echo "!! ${tdir} holds files but no templates - not replacing it." >&2
      echo "!! Move them aside (or point nuclei elsewhere) and re-run." >&2
      rm -rf "$tmp"
      return 1
    fi
  fi
  # mv can still fail (a dangling symlink at $tdir is not -e, so it got past
  # the check above): clean up the temp clone - only $tmp, which this
  # function created - rather than leak one on every run.
  mv "$tmp/t" "$tdir" || { rm -rf "$tmp"; return 1; }
  rmdir "$tmp"
}

install_nmap() {
  already_installed nmap nmap && return 0
  apt_install nmap
}

install_nikto() {
  already_installed nikto nikto probe_nikto && return 0
  apt_install nikto
}

# `nikto --version` is not a nikto option: it prints "Unknown option: version"
# and the usage text, and still exits 0 (measured on nikto 2.6.1), so the
# default probe passes for any nikto that merely starts. `-Version` prints
# "Nikto 2.6.1 (LW 2.5)", so require that version string as well as exit 0.
# Twin of bootstrap.ps1's Test-NiktoRuns.
probe_nikto() {
  local out
  out=$("$1" -Version 2>&1) || return 1
  grep -qiE 'nikto[^0-9]*[0-9]+\.[0-9]+' <<<"$out"
}

install_testssl() {
  # testssl.sh refuses to run at all without hexdump ("Fatal error: You need
  # to install hexdump"), and Ubuntu 24.04 moved it to bsdextrautils, which a
  # minimal image lacks (measured in the Claude Code cloud image).
  command -v hexdump >/dev/null 2>&1 || apt_install bsdextrautils
  already_installed testssl.sh testssl.sh && return 0
  local dir="${OPT_DIR}/testssl.sh"
  if [[ -d "$dir/.git" ]]; then
    sudo env GIT_HTTP_LOW_SPEED_LIMIT=1000 GIT_HTTP_LOW_SPEED_TIME=30 git -C "$dir" pull --ff-only
  else
    sudo rm -rf "$dir"
    sudo env GIT_HTTP_LOW_SPEED_LIMIT=1000 GIT_HTTP_LOW_SPEED_TIME=30 \
      git clone --depth 1 https://github.com/drwetter/testssl.sh.git "$dir"
  fi
  sudo chmod +x "$dir/testssl.sh"
  sudo ln -sf "$dir/testssl.sh" "${BIN_DIR}/testssl.sh"
}

install_trivy() {
  already_installed trivy trivy && return 0
  # Official install script (documented at trivy.dev) - resolves the latest
  # release and puts the binary on the given path itself.
  if curl -sfL "${CURL_API[@]}" https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \
      | sudo sh -s -- -b "${BIN_DIR}"; then
    return 0
  fi
  # That script looks the release up on github.com/<repo>/releases/<tag>,
  # which the same networks that block api.github.com also refuse (even when
  # given an explicit tag), so fall back to the versioned release asset,
  # checked against the release's own checksums file.
  echo ">> trivy: official install script failed - installing the release asset directly" >&2
  install_trivy_asset
}

install_trivy_asset() {
  local arch
  case "$(uname -m)" in
    x86_64|amd64) arch=64bit ;;
    aarch64|arm64) arch=ARM64 ;;
    *) echo "Unsupported arch $(uname -m)"; return 1 ;;
  esac
  local ver
  ver=$(resolve_latest_tag aquasecurity/trivy trivy) || return 1
  local num="${ver#v}"
  local tgz="trivy_${num}_Linux-${arch}.tar.gz" sums="trivy_${num}_checksums.txt"
  local base="https://github.com/aquasecurity/trivy/releases/download/${ver}"

  # Stage under /opt, not /tmp - see install_nuclei for why.
  local stage="${OPT_DIR}/gizmoduck-trivy-download"
  sudo rm -rf "$stage"
  sudo mkdir -p "$stage"
  sudo curl -fsSL "${CURL_DL[@]}" -o "$stage/$tgz" "$base/$tgz"
  sudo curl -fsSL "${CURL_API[@]}" -o "$stage/$sums" "$base/$sums"
  verify_sha256 "$stage" "$tgz" "$sums" || { sudo rm -rf "$stage"; return 1; }
  sudo tar -xzf "$stage/$tgz" -C "$stage" trivy
  sudo mv "$stage/trivy" "${BIN_DIR}/trivy"
  sudo chmod +x "${BIN_DIR}/trivy"
  sudo rm -rf "$stage"
  echo ">> installed: $("${BIN_DIR}/trivy" --version 2>&1 | head -1)"
}

install_checkov() {
  already_installed checkov checkov && return 0
  pip3 install --user --upgrade checkov
}

install_semgrep() {
  already_installed semgrep semgrep && return 0
  # Semgrep is the only source-reading tool here, and the only one that can
  # see a check that is MISSING - an authorization gate nobody wrote has no
  # signature, no CVE and no misconfigured resource to find.
  pip3 install --user --upgrade semgrep
}

install_depcheck() {
  already_installed dependency-check dependency-check && return 0
  local ver
  ver=$(resolve_latest_tag jeremylong/DependencyCheck "dependency-check") || return 1
  local num="${ver#v}"
  local zip="dependency-check-${num}-release.zip"

  # Stage next to the extraction target (/opt) instead of /tmp - see
  # install_nuclei above for why.
  sudo curl -fsSL "${CURL_DL[@]}" -o "${OPT_DIR}/$zip" \
    "https://github.com/jeremylong/DependencyCheck/releases/download/${ver}/${zip}"
  sudo unzip -oq "${OPT_DIR}/$zip" -d "${OPT_DIR}"
  sudo rm -f "${OPT_DIR}/$zip"
  sudo chmod +x "${OPT_DIR}/dependency-check/bin/dependency-check.sh"
  sudo ln -sf "${OPT_DIR}/dependency-check/bin/dependency-check.sh" "${BIN_DIR}/dependency-check"

  # Dependency-Check is a Java app; make sure something can run it.
  command -v java >/dev/null 2>&1 || apt_install default-jre
}

install_sqlmap() {
  already_installed sqlmap sqlmap && return 0
  # git clone is sqlmap's own documented install method - there is no PyPI
  # package (spec 13.9: no --report-json either, but that's a routine.py
  # adapter concern, not a bootstrap one).
  local dir="${OPT_DIR}/sqlmap"
  if [[ -d "$dir/.git" ]]; then
    sudo env GIT_HTTP_LOW_SPEED_LIMIT=1000 GIT_HTTP_LOW_SPEED_TIME=30 git -C "$dir" pull --ff-only
  else
    sudo rm -rf "$dir"
    sudo env GIT_HTTP_LOW_SPEED_LIMIT=1000 GIT_HTTP_LOW_SPEED_TIME=30 \
      git clone --depth 1 https://github.com/sqlmapproject/sqlmap.git "$dir"
  fi
  sudo tee "${BIN_DIR}/sqlmap" >/dev/null <<EOS
#!/usr/bin/env bash
exec python3 "${dir}/sqlmap.py" "\$@"
EOS
  sudo chmod +x "${BIN_DIR}/sqlmap"
}

install_zap() {
  # ZAP 2.16+ requires Java 17 minimum (spec 13.3). A missing or too-old JRE
  # lets this install step "succeed" while ZAP itself refuses to start later -
  # which looks like a missing tool for reasons nobody can see from `doctor`.
  # Check for 17+ before doing anything else, matching the JRE gate ZAP needs.
  if ! java -version 2>&1 | grep -qE '"(1\.)?(1[7-9]|[2-9][0-9])'; then
    apt_install openjdk-17-jre
  fi

  already_installed "OWASP ZAP" zap.sh probe_zap && return 0

  # The Crossplatform zip ships both zap.sh and zap.bat plus the Automation
  # Framework add-on, so the same download works for bootstrap.ps1 too. This
  # is a plain unzip, not the docker `zaproxy/zap-stable` image - Docker is
  # not installed on the operator machine and using it here was explicitly
  # ruled out (do not "fix" this back to a docker run).
  local ver
  ver=$(resolve_latest_tag zaproxy/zaproxy "OWASP ZAP") || return 1
  local num="${ver#v}"
  local zip="ZAP_${num}_Crossplatform.zip"

  # Stage next to the extraction target (/opt) instead of /tmp - a 286MB ZAP
  # zip sitting in /tmp mid-download is exactly what got flagged and
  # quarantined by Defender on Windows; /tmp is the equivalent risk here.
  sudo curl -fsSL "${CURL_DL[@]}" -o "${OPT_DIR}/$zip" \
    "https://github.com/zaproxy/zaproxy/releases/download/${ver}/${zip}"
  sudo unzip -oq "${OPT_DIR}/$zip" -d "${OPT_DIR}"
  sudo rm -f "${OPT_DIR}/$zip"
  sudo chmod +x "${OPT_DIR}/ZAP_${num}/zap.sh"
  sudo ln -sf "${OPT_DIR}/ZAP_${num}/zap.sh" "${BIN_DIR}/zap.sh"
}

# `zap.sh -version` starts a JVM (seconds), so the skip check looks for what
# a half-unpacked zip would lack instead: the launcher's own zap-<ver>.jar.
probe_zap() {
  local real
  real=$(readlink -f "$1") || return 1
  compgen -G "$(dirname "$real")/zap-*.jar" >/dev/null
}

# Sourced rather than executed (the test suite does this to reach
# resolve_latest_tag): stop here, defining the functions and installing nothing.
# `return` outside a function succeeds only in a sourced file, which is a
# sturdier test than comparing BASH_SOURCE with $0 (`bash -c 'source "$0"' f`
# makes those equal while sourcing).
if (return 0 2>/dev/null); then
  return 0
fi

try_install "prerequisites"      install_prereqs
try_install "nuclei"             install_nuclei
update_nuclei_templates          # hard-fail exception - see comment above, do not wrap in try_install
try_install "nmap"               install_nmap
try_install "nikto"              install_nikto
try_install "testssl.sh"         install_testssl
try_install "trivy"              install_trivy
try_install "checkov"            install_checkov
try_install "semgrep"            install_semgrep
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

 For the full scanner routine across a manifest of targets:
   python3 scripts/gizmoduck.py routine targets.yaml --scan-root .   (then /gizmoduck:doctor confirms what installed)
------------------------------------------------------------
MSG
