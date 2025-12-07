# Putio-Get
A downloader for content stored in put.io.
It allows you to sync a put.io directory locally when new files are added.


**This is not affiliated with nor supported by put.io**

# Docker Compose
```yaml
services:
  putio-get:
    image: jokneemo/putio-get:latest
    restart: unless-stopped
    privileged: true
    devices:
      - "/dev/fuse:/dev/fuse"
    environment:
      PUTIO_USERNAME: yourgenericusername
      PUTIO_PASSWORD: your-super-secret-password-or-app-password
      PUTIO_SYNC_ACTION: move
      PUTIO_GUESSIT: true
      DAV_MAP: "/Videos:/Videos,/Comics:/Literature/Comics"
    volumes:
      - ./local-media:/target
```

# Container Variables
Environment variables can control several behaviors in the container

| Variable | Default Value | Description |
|---|---|---|
| PUTIO_DOMAIN | https://webdav.put.io | The WebDAV endpoint |
| PUTIO_USERNAME | - | Your put.io username |
| PUTIO_PASSWORD | - | Your put.io password |
| PUTIO_POLL_INTERVAL_SECONDS | 30 | How often to check for new content, in seconds |
| PUTIO_SYNC_ACTION | copy | What action to take when new content is detected, copy or move. Using move will send the file to put.io's trash after it's copied to your target directory |
| PUTIO_TARGET | /target | The directory inside the container where new content will be copied or moved to |
| PUTIO_GUESSIT | false | Whether to rename files to match their metadata |
| PUTIO_SKIP_EXISTING | false | Whether to skip existing files in source (when the loop starts) |
| PUTIO_FILETYPES | mkv,mp4,avi,mov,wmv,flv,webm,srt,sub,sbv,vtt,ass,mp3,flac,aac,wav,m4a,ogg | Comma-separated list of allowed file extensions |
| PUTIO_DEBUG | false | Enable debug logging |
| DAV_MAP | - | A comma separated mapping of `source:target` directories. If this variable exists, only the `source` directories will be monitored. The content will be placed in the `target` directory, duplicating the directory structure. |
| DAV_MOUNT | /dav | The directory inside the container where the put.io WebDav directory will be mounted. This could also be a bind mount so that you can access your put.io directory outside of the container, or with another container. |
| DAV_UID | 1000 | The user ID that all content will be written as. |
| DAV_GID | 1000 | The group ID that all content will be written as. |
| DAV_DMODE | 755 | The permission mode all directories will be created with. |
| DAV_FMODE | 755 | The permission mode all files will be created with. |
| DAVFS2_* | - | Any config option available for davfs2.conf. The variable name must start with `DAVFS2_`. |