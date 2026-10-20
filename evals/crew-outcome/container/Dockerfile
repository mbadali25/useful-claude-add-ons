# L-0728 outcome eval arm image. Claude Code and Codex are pinned; the repo's
# own test dependencies are pytest only (hidden tests run outside this image).
# Build with the host network (`docker build --network host -t crew-outcome-eval:1 .`):
# this host forwards no container traffic, so a default-network build cannot reach apt or npm.
FROM node:22-bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates curl python3 python3-pytest python3-yaml \
 && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code@2.1.303 @openai/codex@0.162.1 \
 && npm cache clean --force

COPY codex-shim.sh /opt/eval-shim/codex
ENV PATH=/opt/eval-shim:$PATH

# The base image's `node` user is uid 1000. Claude Code refuses
# --dangerously-skip-permissions as root, so an arm never runs as root.
USER node
WORKDIR /run/repo
