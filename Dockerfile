#ARG ARCH=
FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim AS python-builder
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /botamusique

RUN apt-get update \
    && apt-get install --no-install-recommends -y gcc g++ ffmpeg libjpeg-dev libmagic-dev opus-tools zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*


COPY . /botamusique
RUN uv venv --clear \
    && uv sync --no-dev

FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install --no-install-recommends -y opus-tools ffmpeg libmagic-dev curl tar && \
    rm -rf /var/lib/apt/lists/*

COPY --from=denoland/deno:bin-2.5.6 /deno /usr/local/bin/deno
RUN chmod +x /usr/local/bin/deno
RUN deno --version
# check quickjs as alternative : https://github.com/yt-dlp/yt-dlp/wiki/EJS#quickjs--quickjs-ng
COPY --from=python-builder /botamusique /botamusique
WORKDIR /botamusique
COPY --chmod=+x entrypoint2.sh /botamusique/entrypoint2.sh

ENTRYPOINT [ "/bin/sh", "/botamusique/entrypoint2.sh" ]
CMD ["venv/bin/python", "mumbleBot.py"]
