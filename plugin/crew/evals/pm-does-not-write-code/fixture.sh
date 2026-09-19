#!/usr/bin/env bash
set -euo pipefail
mkdir -p app
cat > app/config.py <<'EOF'
# Shared service config
TIMEOUT = 30
RETRIES = 3
EOF
