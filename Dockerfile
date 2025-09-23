#ARG ARCH=
FROM python:3.11-alpine AS python-builder
WORKDIR /botamusique

RUN apk upgrade \
    && apk add --no-cache gcc g++ ffmpeg jpeg-dev libmagic opus opus-tools zlib-dev
COPY . /botamusique
RUN python3 -m venv venv \
    && venv/bin/pip install wheel \
    && venv/bin/pip install ./pymumble \
    && venv/bin/pip install -r requirements.txt

FROM python:3.11-alpine
RUN apk upgrade --no-cache && \
    apk add --no-cache opus-tools ffmpeg libmagic curl tar
COPY --from=python-builder /botamusique /botamusique
WORKDIR /botamusique
COPY --chmod=+x entrypoint2.sh /botamusique/entrypoint2.sh

ENTRYPOINT [ "/bin/sh", "/botamusique/entrypoint2.sh" ]
CMD ["venv/bin/python", "mumbleBot.py"]
