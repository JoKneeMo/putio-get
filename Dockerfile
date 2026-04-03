FROM alpine:latest

LABEL org.opencontainers.image.title=putio-get \
    org.opencontainers.image.authors="JokneeMo <github.com/JokneeMo>" \
    org.opencontainers.image.licenses="AGPL-3.0" \
    org.opencontainers.image.description="A downloader for content stored in put.io." \
    org.opencontainers.image.url="https://github.com/JokneeMo/putio-get"

RUN apk add --no-cache \
        bash \
        aria2 \
        ca-certificates \
        python3 \
        py3-pip \
        tini \
    && pip install --upgrade --no-cache-dir --break-system-packages \
        pip \
        setuptools \
        wheel


ENV COLUMNS=120

COPY --chown=1000:101 . /app/
WORKDIR /app

RUN pip install --break-system-packages --no-cache-dir .

ENTRYPOINT [ "tini", "-g", "--", "putio-get"]
CMD ["--daemon"]
