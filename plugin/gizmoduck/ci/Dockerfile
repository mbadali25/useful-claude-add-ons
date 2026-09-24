# gizmoduck CI runner image - every scanner bootstrap.sh installs, baked in once
# so a pipeline run does not reinstall nine tools and the Nuclei template feed.
#
# Build from the plugin directory (the build context must be plugin/gizmoduck).
# Needs BuildKit (docker buildx; the default builder since Docker 23) for the
# secret mount below:
#
#   cd plugin/gizmoduck
#   docker build -f ci/Dockerfile -t ghcr.io/<owner>/gizmoduck-ci:<version> .
#
# <version> is the plugin version in .claude-plugin/plugin.json. The rendered
# pipelines reference exactly that tag, so push one tag per release and never
# move it:
#
#   echo "$GHCR_TOKEN" | docker login ghcr.io -u <owner> --password-stdin
#   docker push ghcr.io/<owner>/gizmoduck-ci:<version>
#
# Docker Hub works the same way (docker.io/<user>/gizmoduck-ci:<version>);
# pass the reference to `gizmoduck_ci.py render --image`. A private image
# needs registry credentials on the runner (GitHub: jobs.<id>.container.
# credentials; Bitbucket: image.username/password).
#
# Optional NVD pre-sync: Dependency-Check's first run downloads the whole NVD
# corpus, which can exceed its adapter timeout on a cold runner. Build with
#   docker build --build-arg GIZMODUCK_NVD_PRESYNC=1 \
#     --secret id=nvd_api_key,env=NVD_API_KEY -f ci/Dockerfile -t ... .
# The key is mounted for that one RUN and is never written to a layer.
#
# Without the image, the rendered pipelines fall back to running this same
# bootstrap.sh inline (GitHub: repository variable GIZMODUCK_RUNNER=bootstrap;
# Bitbucket: the *-bootstrap custom pipelines).
FROM ubuntu:24.04

ARG GIZMODUCK_NVD_PRESYNC=0

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    PYTHONUSERBASE=/root/.local \
    GIZMODUCK_HOME=/opt/gizmoduck \
    GIZMODUCK_NUCLEI_TEMPLATES=/opt/nuclei-templates \
    PATH=/root/.local/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN apt-get update \
 && apt-get install -y --no-install-recommends sudo ca-certificates curl git unzip jq \
      python3 python3-pip python3-yaml \
 && rm -rf /var/lib/apt/lists/*

COPY bootstrap.sh /opt/gizmoduck/bootstrap.sh
RUN bash /opt/gizmoduck/bootstrap.sh \
 && mv /root/nuclei-templates /opt/nuclei-templates \
 && ln -s /opt/nuclei-templates /root/nuclei-templates \
 && chmod -R a+rX /opt/nuclei-templates /root/.local \
 && chmod a+x /root \
 && rm -rf /var/lib/apt/lists/*

RUN --mount=type=secret,id=nvd_api_key,required=false \
    if [ "$GIZMODUCK_NVD_PRESYNC" = "1" ]; then \
      key=""; [ -f /run/secrets/nvd_api_key ] && key="$(cat /run/secrets/nvd_api_key)"; \
      if [ -n "$key" ]; then dependency-check --updateonly --nvdApiKey "$key"; \
      else dependency-check --updateonly; fi; \
    fi

COPY scripts /opt/gizmoduck/scripts
COPY .claude-plugin /opt/gizmoduck/.claude-plugin

RUN python3 /opt/gizmoduck/scripts/gizmoduck.py doctor || true
