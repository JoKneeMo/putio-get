FROM alpine:latest

LABEL org.opencontainers.image.title=putio-get \
    org.opencontainers.image.authors="JokneeMo <github.com/JokneeMo>" \
    org.opencontainers.image.licenses="AGPL-3.0" \
    org.opencontainers.image.description="A downloader for content stored in put.io." \
    org.opencontainers.image.source="https://github.com/JokneeMo/putio-get" \
    org.opencontainers.image.url="https://github.com/JokneeMo/putio-get"

RUN apk --no-cache add \
    bash \
    ca-certificates \
    davfs2 \
    python3 \
    tini \
    py3-pip \
    && adduser -D -u 1000 -G davfs2 davfs2

# PUTIO Sync Environment Variables
ENV PUTIO_DOMAIN=https://webdav.put.io \
    PUTIO_USERNAME= \
    PUTIO_USERNAME_FILE= \
    PUTIO_PASSWORD= \
    PUTIO_PASSWORD_FILE= \
    PUTIO_TARGET=/target \
    PUTIO_POLL_INTERVAL_SECONDS=30 \
    PUTIO_SYNC_ACTION=copy \
    PUTIO_GUESSIT=false \
    PUTIO_SKIP_EXISTING=false \
    DAV_MAP= \
    DAV_MOUNT=/dav \
    DAV_UID=1000 \
    DAV_GID=1000 \
    DAV_DMODE=755 \
    DAV_FMODE=755

# DAVFS2 Environment Variables
ENV DAVFS2_FOLLOW_REDIRECT=1 \
    DAVFS2_USE_COMPRESSION=1 \
    DAVFS2_ASK_AUTH=0 \
    DAVFS2_DAV_USER=davfs2 \
    DAVFS2_DAV_GROUP=davfs2

COPY --chown=1000:101 *.sh *.py requirements.txt /

RUN pip install --break-system-packages --no-cache-dir -r requirements.txt

ENTRYPOINT [ "tini", "-g", "--", "/docker-entrypoint.sh"]
CMD ["/usr/bin/python3", "-u", "/putio-get.py"]
