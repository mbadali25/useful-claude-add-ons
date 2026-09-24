# gizmoduck CI runner image - every scanner bootstrap.sh installs, baked in once
# so a pipeline run does not reinstall nine tools and the Nuclei template feed.
#
# Build from the plugin directory (the build context must be plugin/gizmoduck).
# Needs BuildKit (docker buildx; the default builder since Docker 23) for the
# secret mount below. The base image is pinned by DIGEST, never by tag: a tag
# is a pointer its owner can move, so rebuilding the same release from
# `ubuntu:24.04` could silently take different base contents. Resolve the
# digest once per release, record it in the release notes, and pass it:
#
#   cd plugin/gizmoduck
#   digest="$(docker buildx imagetools inspect ubuntu:24.04 --format '{{json .Manifest.Digest}}' | tr -d '"')"
#   docker build --build-arg GIZMODUCK_BASE_DIGEST="$digest" \
#     -f ci/Dockerfile -t ghcr.io/<owner>/gizmoduck-ci:<version> .
#
# Without the argument, or with anything but a sha256 digest, the build fails.
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
ARG GIZMODUCK_BASE_DIGEST
FROM ubuntu:24.04@${GIZMODUCK_BASE_DIGEST}

ARG GIZMODUCK_BASE_DIGEST
ARG GIZMODUCK_NVD_PRESYNC=0
LABEL org.opencontainers.image.base.name="docker.io/library/ubuntu:24.04" \
      org.opencontainers.image.base.digest="${GIZMODUCK_BASE_DIGEST}"

RUN case "${GIZMODUCK_BASE_DIGEST}" in \
      sha256:????????????????????????????????????????????????????????????????) ;; \
      *) echo "GIZMODUCK_BASE_DIGEST must be the base image's sha256 digest; got '${GIZMODUCK_BASE_DIGEST}'" >&2; exit 1 ;; \
    esac

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

# The image is only as good as its toolchain: doctor must pass and every
# scanner adapter must be runnable, or the build fails here rather than
# shipping an image whose scans record tools as skipped-missing.
RUN python3 /opt/gizmoduck/scripts/gizmoduck_ci.py image-check
