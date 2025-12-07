FROM alpine:latest

LABEL MAINTAINER=JokneeMo \
    VERSION=1.2.0

RUN apk --no-cache add \
    bash \
    ca-certificates \
    davfs2 \
    python3 \
    py3-tqdm \
    tini \
    py3-guessit \
    && adduser -D -u 1000 -G davfs2 davfs2

# PUTIO Sync Environment Variables
ENV PUTIO_DOMAIN=https://webdav.put.io \
    PUTIO_USERNAME= \
    PUTIO_PASSWORD= \
    PUTIO_TARGET=/target \
    PUTIO_POLL_INTERVAL_SECONDS=30 \
    PUTIO_SYNC_ACTION=copy \
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
    DAVFS2_DAV_GROUP=davfs2 \
    PYTHONUNBUFFERED=1

COPY --chown=1000:101 *.sh *.py /

ENTRYPOINT [ "tini", "-g", "--", "/docker-entrypoint.sh"]
CMD ["/usr/bin/python3", "-u", "/putio-get.py"]
