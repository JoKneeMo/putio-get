# Putio-Get
A downloader for content stored in put.io.

It allows you to sync a put.io directory locally when new files are added.

This was created for my own purposes, it's not perfect, but it works for MY needs.

Available on Docker Hub: https://hub.docker.com/r/jokneemo/putio-get

**This is not affiliated with nor supported by put.io**

# Python Package
You can install `putio-get` directly from PyPI (or local source):

```bash
pip install putio-get
```

Usage:
```bash
# Run once and exit
putio-get

# Run as a daemon (monitoring loop)
putio-get --daemon
```

# Docker Compose
```yaml
services:
  putio-get:
    image: jokneemo/putio-get:latest
    restart: unless-stopped
    environment:
      PUTIO_OAUTH_TOKEN: 'your-oauth-token-here'
      PUTIO_SYNC_ACTION: move
      PUTIO_EMPTY_TRASH: true
      PUTIO_GUESSIT: true
      PUTIO_DIRECTORY_MAP: "/Videos:/Videos,/Comics:/Literature/Comics"
    volumes:
      - ./local-media:/target
```

# Getting an OAuth Token
You can get a put.io OAuth token for this system by navigating to https://app.put.io/oauth.
1. Click `Create App` in the top right corner
2. Fill in the form:
    | Field | Value |
    | --- | --- |
    | Application Name | putio-get|
    | Description | A python service to automatically download files from put.io |
    | Application website | https://github.com/JokneeMo/putio-get |
    | Callback URL | * |
    | Don't show in Extensions page | [x] |
3. Then click `Create App`
4. Copy the values of the `OAuth token`, this is the only thing that will be needed.


# Container Variables
Environment variables can control several behaviors in the container

## Required Variables
> [!IMPORTANT]
> You must provide one of either the main or `_FILE` variables for each of the following in this table

| Variable | Command Argument | Default Value | Description |
|  :----:  | :----: | :----         | :----       |
| **PUTIO_OAUTH_TOKEN** | `--oauth-token` | - | Your put.io OAuth Token |
| **PUTIO_OAUTH_TOKEN_FILE** | - | - | File path to your put.io OAuth Token |

## Optional Variables
| Variable | Command Argument | Default Value | Description |
|  :----:  | :----: | :----         | :----       |
| **PUTIO_CONFIG_FILE** | - | - | File path to a json config file. All options can be set in this file instead of defining each one. If this file is set, environment variables will be ignored, but additional runtime arguments will override it. |
| **PUTIO_POLL_INTERVAL_SECONDS** | `--poll-interval` | 300 | How often to check for new content, in seconds, when daemon mode is enabled |
| **PUTIO_SYNC_ACTION** | `--action` | copy | What action to take when new content is detected, copy or move. Using move will send the file to put.io's trash after it's copied to your target directory |
| **PUTIO_TARGET** | `--target` | /target | The directory inside the container where new content will be copied or moved to |
| **PUTIO_GUESSIT** | `--guessit` | true | Try to rename files to match their metadata |
| **PUTIO_DIRECTORY_MAP** | `--map` | - | A comma separated mapping of `source:target` directories. If this variable exists, only the `source` directories will be monitored. The content will be placed in the `target` directory, duplicating the directory structure. |
| **PUTIO_SKIP_EXISTING** | `--skip-existing` | false | Skip existing files in source (when the loop starts) |
| **PUTIO_FILETYPES** | `--filetypes` | mkv, mp4, avi, mov, wmv, flv, webm, srt, sub, sbv, vtt, ass, mp3, flac, aac, wav, m4a, ogg | Comma-separated list of allowed file extensions |
| **LOG_LEVEL** | `--log-level` | INFO | The logging level. TRACE, DEBUG, INFO, WARNING, ERROR, CRITICAL |
| **PUTIO_MAX_SEGMENTS** | `--max-segments` | 8 | Maximum number of connections per download |
| **PUTIO_MIN_SEGMENT_SIZE** | `--min-segment-size` | 50MB | Minimum segment size for downloads (e.g. 5MB, 10MB) |
| **PUTIO_MAX_CONCURRENT_DOWNLOADS** | `--max-concurrent-downloads` | 3 | Maximum number of concurrent downloads |
| **PUTIO_ENABLE_MIRRORS** | `--enable-mirrors` | false | Enable use of additional mirrors for downloads |
| **PUTIO_MIN_MIRROR_SPEED** | `--min-mirror-speed` | - | Minimum speed required for a mirror to be used (e.g., 5MB/s, 50MB/s) |
| **PUTIO_BENCHMARK_ONLY** | `--benchmark-only` | false | Run mirror benchmarks, save results, and exit |
| **PUTIO_BENCHMARK_FILE** | `--benchmark-file` | mirror_speeds.json | File path to save/load benchmark results |
| **PUTIO_EMPTY_TRASH** | `--empty-trash` | false | Empty put.io trash after moving files to target directory. Only used when action is `move` |


# Mirror Usage
Using the put.io mirrors can significantly speed up downloads.
Mirror usage is disabled by default.

To benchmark the mirrors, run the following command:

**localhost**:
```bash
putio-get --benchmark-only --benchmark-file ./mirror_speeds.json --min-mirror-speed 50MB/s
```

**Docker**:
```bash
docker run --rm -v ./mirror_speeds.json:/mirror_speeds.json jokneemo/putio-get:latest --benchmark-only --benchmark-file /mirror_speeds.json --min-mirror-speed 50MB/s
```

To use the mirrors at runtime, use the argument `--enable-mirrors` or set the environment variable `PUTIO_ENABLE_MIRRORS=true`.
Use the argument `--min-mirror-speed` or set the environment variable `PUTIO_MIN_MIRROR_SPEED=50MB/s` (or desired speed) to the minimum speed required for a mirror to be used.

Be sure to mount the benchmark file to the container if you want to use the same benchmark results across restarts. Otherwise, the mirrors will be benchmarked on every startup.

The default location of the benchmark file is `/mirror_speeds.json` inside the container.
Use the argument `--benchmark-file` or environment variable `PUTIO_BENCHMARK_FILE` to specify a different location.


# Config File
You can define all, or only some, of the options in a json file. The file can be specified using the `--config-file` argument or the `PUTIO_CONFIG_FILE` environment variable.
If the file is specified and loaded successfully, it can still be overridden by environment variables, which in turn can be overridden by runtime arguments.

To get the config file format, run the following command:

**localhost**:
```bash
putio-get --print-config
```

**Docker**:
```bash
docker run --rm jokneemo/putio-get:latest --print-config
```

This will print the default config file format to the console.

The `--print-config` argument can also accept a comma separated list of config sections to print.

```bash
putio-get --print-config paths,permissions
```

This will print the config for the paths and permissions sections to the console. You can then store this in a file and use it as needed.
