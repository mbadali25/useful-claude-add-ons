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

cat <<'MSG'

------------------------------------------------------------
 Nuclei is ready. Try:
   nuclei -u https://example.com -severity critical,high

 Or drive it through the plugin:
   /gizmoduck:scan https://your-new-site.com high
------------------------------------------------------------
MSG
