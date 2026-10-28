FROM ghcr.io/astral-sh/uv:0.13.6-python3.15-trixie-slim AS python-builder
ENV DEBIAN_FRONTEND=noninteractive
ARG GIT_COMMIT
WORKDIR /botamusique

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates gcc g++ ffmpeg libjpeg-dev opus-tools zlib1g-dev \
    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' ca-certificates)" ge "20250419+deb13u1" \
    && rm -rf /var/lib/apt/lists/*


RUN python -m pip install --no-cache-dir --upgrade "pip>=26.2.2"

COPY . /botamusique
RUN uv venv --clear \
    && uv sync --no-dev \
    && uv run --group build scripts/build.py


FROM ghcr.io/astral-sh/uv:0.13.6-python3.15-trixie-slim
ENV DEBIAN_FRONTEND=noninteractive
ARG GIT_COMMIT
ENV GIT_COMMIT=${GIT_COMMIT}

RUN apt-get update && \
    apt-get install --no-install-recommends -y ca-certificates opus-tools ffmpeg curl tar && \
    dpkg --compare-versions "$(dpkg-query -W -f='${Version}' ca-certificates)" ge "20250419+deb13u1" && \
    rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir --upgrade "pip>=26.2.2"

COPY --from=docker.io/denoland/deno:bin-2.9.8 /deno /usr/local/bin/deno
RUN chmod +x /usr/local/bin/deno
RUN deno --version
# check quickjs as alternative : https://github.com/yt-dlp/yt-dlp/wiki/EJS#quickjs--quickjs-ng
COPY --from=python-builder /botamusique /botamusique
WORKDIR /botamusique

RUN groupadd -g 568 usergroup
RUN useradd -u 568 -g usergroup -ms /bin/sh bota
USER bota

CMD ["uv", "run", "--locked", "--no-dev", "--no-sync", "botamusique"]
