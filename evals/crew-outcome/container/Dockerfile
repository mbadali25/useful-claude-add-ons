# L-0728 outcome eval arm image. Claude Code and Codex are pinned; the repo's
# own test dependencies are pytest only (hidden tests run outside this image).
# Build with the host network (`docker build --network host -t crew-outcome-eval:1 .`):
# this host forwards no container traffic, so a default-network build cannot reach apt or npm.
# The base is pinned by digest. Claude Code 2.1.303 needs its postinstall (no --ignore-scripts), so npm
# transitive dependencies and apt packages float at build time; the canary records the image id it vouches for.
FROM node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates curl python3 python3-pytest python3-yaml \
 && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code@2.1.303 @openai/codex@0.162.1 \
 && npm cache clean --force

COPY codex-shim.sh /opt/eval-shim/codex
COPY eval-run.py /opt/eval-shim/eval-run
RUN chmod 0755 /opt/eval-shim/codex /opt/eval-shim/eval-run
ENV PATH=/opt/eval-shim:$PATH

# The base image's `node` user is uid 1000. Claude Code refuses
# --dangerously-skip-permissions as root, so an arm never runs as root.
USER node
WORKDIR /run/repo
