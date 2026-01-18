FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim AS python-builder
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /botamusique

RUN apt-get update \
    && apt-get install --no-install-recommends -y gcc g++ ffmpeg libjpeg-dev libmagic-dev opus-tools zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*


COPY . /botamusique
RUN uv venv --clear \
    && uv sync --no-dev


# FIXME: node 14 is ancient, migrate to node 24!
FROM node:18-bullseye-slim AS node-builder
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /botamusique/web
COPY --from=python-builder /botamusique/web .
RUN npm install
RUN npm run build


FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim AS template-builder
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /botamusique
COPY --from=python-builder /botamusique .
COPY --from=node-builder /botamusique/templates templates
RUN uv run --no-dev scripts/translate_templates.py --lang-dir /botamusique/lang --template-dir /botamusique/web/templates


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
COPY --from=node-builder /botamusique/static static
COPY --from=template-builder /botamusique/templates templates
WORKDIR /botamusique

RUN groupadd -g 568 usergroup
RUN useradd -u 568 -g usergroup -ms /bin/sh bota
USER bota

CMD ["uv", "run", "--locked", "--no-dev", "main.py"]
