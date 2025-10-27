#ARG ARCH=
FROM python:3.11-alpine AS python-builder
WORKDIR /botamusique

# Explicitly install ca-certificates
RUN apk add --no-cache openssl openssl-dev ca-certificates
# Update the trust store
RUN update-ca-certificates

RUN apk upgrade \
    && apk add --no-cache gcc g++ libmagic jpeg-dev zlib-dev

COPY . /botamusique
RUN python3 -m venv venv \
    && venv/bin/pip install wheel \
    && venv/bin/pip install -r requirements.txt

FROM python:3.11-alpine

# Explicitly install ca-certificates
RUN apk add --no-cache openssl openssl-dev ca-certificates
# Update the trust store
RUN update-ca-certificates

RUN apk upgrade --no-cache && \
    apk add --no-cache opus opus-tools ffmpeg jpeg-dev libmagic curl tar

# Set LD_LIBRARY_PATH in the runtime image
ENV LD_LIBRARY_PATH=/usr/local/lib:/usr/lib:/usr/lib/x86_64-linux-gnu
RUN ln -s /usr/lib/libopus.so.0 /usr/local/lib/libopus.so.0

COPY --from=python-builder /botamusique /botamusique
WORKDIR /botamusique
COPY --chmod=+x entrypoint2.sh /botamusique/entrypoint2.sh

ENTRYPOINT [ "/bin/sh", "/botamusique/entrypoint2.sh" ]
CMD ["venv/bin/python", "mumbleBot.py"]
