import time
import subprocess
import logging
import aria2p
from importlib.metadata import version
from urllib.parse import urlparse, urlunparse
from pathlib import Path
from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
    DownloadColumn
)
from .config import Config

log = logging.getLogger("rich")


class Downloader:
    def __init__(self, config: Config, sorted_mirrors: list[dict] = None):
        self.config = config
        self.sorted_mirrors = sorted_mirrors or []
        self.aria2: aria2p.API = None
        self._init_aria2()

    def _init_aria2(self):
        try:
            self.aria2 = aria2p.API(
                aria2p.Client(
                    host="http://localhost",
                    port=6800,
                    secret=""
                )
            )
            self.aria2.client.get_version()
            log.info("Connected to existing downloader daemon.")
        except Exception:
            log.info("Starting internal downloader daemon...")
            cmd = [
                "aria2c",
                "--enable-rpc",
                "--rpc-listen-all=false",
                "--rpc-listen-port=6800",
                "--daemon",
                f"--max-concurrent-downloads={self.config.download['max_concurrent']}",
                "--max-connection-per-server=16",
                "--split=16",
                "--continue=true",
                f"--user-agent=putio-get/{version('putio-get')}"
            ]
            subprocess.run(cmd, check=True)
            time.sleep(1)
            self.aria2 = aria2p.API(
                aria2p.Client(
                    host="http://localhost",
                    port=6800,
                    secret=""
                )
            )

    def download(self, url: str, dst_path: Path, file_size: int, exit_event, sha1: str = None) -> bool:
        segments = 1
        if file_size > 0:
            possible_segments = file_size // self.config.download['min_segment_size_bytes']
            segments = max(1, min(self.config.download['max_segments'], possible_segments))

        log.info(f"Downloading: {dst_path.name} (Size: {file_size/1024/1024:.2f} MB, Segments: {segments})")

        uris = self._build_uris(url)

        options = {
            "dir": str(dst_path.parent),
            "out": dst_path.name,
            "split": str(segments),
            "min-split-size": str(self.config.download['min_segment_size']),
            "allow-overwrite": "true"
        }

        if sha1:
            options["check-integrity"] = "true"
            options["checksum"] = f"sha-1={sha1}"

        try:
            # Aria2 returns GID or Download object depending on version/mock
            new_download = self.aria2.add_uris(uris, options=options)

            if isinstance(new_download, str):
                gid = new_download
                download = self.aria2.get_download(gid)
            else:
                download = new_download
                gid = download.gid

            self._monitor_download(download, dst_path, exit_event)
        except Exception as e:
            log.error(f"Download failed for {dst_path}: {e}")
            if gid:
                try: self.aria2.remove([gid])
                except: pass
            return False

        if exit_event.is_set():
            return False

        return True

    def _build_uris(self, primary_url):
        mirrors = []
        if self.config.mirrors['enabled']:
            parsed_url = urlparse(primary_url)

            # mirrors map from config
            mirror_list = self.sorted_mirrors if self.sorted_mirrors else [{'name': k, 'code': v} for k, v in self.config.mirrors['map'].items()]

            for mirror_info in mirror_list:
                code = mirror_info['code']
                host = f"{code}.put.io"
                if parsed_url.netloc == host: continue

                mirror_url = urlunparse((
                    parsed_url.scheme, host, parsed_url.path,
                    parsed_url.params, parsed_url.query, parsed_url.fragment
                ))
                mirrors.append(mirror_url)

        # Optimize order
        uris = [primary_url] + mirrors
        if self.sorted_mirrors and self.config.mirrors['enabled']:
            best_mirror = self.sorted_mirrors[0]
            best_host = f"{best_mirror['code']}.put.io"
            parsed_primary = urlparse(primary_url)

            if parsed_primary.netloc != best_host:
                log.info(f"Using fastest mirror ({best_mirror['name']}) as primary.")
                best_mirror_url = urlunparse((
                    parsed_primary.scheme, best_host, parsed_primary.path,
                    parsed_primary.params, parsed_primary.query, parsed_primary.fragment
                ))
                mirrors = [m for m in mirrors if m != best_mirror_url]
                uris = [best_mirror_url, primary_url] + mirrors

        return uris

    def _monitor_download(self, download, dst_path, exit_event):
        progress = Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            transient=True,
            refresh_per_second=2
        )

        with progress:
            task_id = progress.add_task(f"Downloading: {dst_path.name}", total=None)
            while not exit_event.is_set():
                download.update()
                status = download.status

                if status == "active":
                    if download.total_length > 0:
                        progress.update(task_id, total=download.total_length, completed=download.completed_length, speed=download.download_speed)
                elif status == "complete":
                    progress.update(task_id, total=download.total_length, completed=download.completed_length)
                    log.info(f"Download complete: {dst_path.name}")
                    download.remove()
                    # Cleanup .aria2 file
                    aria2_file = dst_path.with_suffix(dst_path.suffix + ".aria2")
                    if aria2_file.exists():
                        aria2_file.unlink()
                    break
                elif status == "error":
                    log.error(f"Aria2 error for {dst_path.name}: {download.error_message}")
                    download.remove()
                    raise Exception(f"Aria2 download failed: {download.error_message}")
                elif status == "removed":
                    log.warning(f"Download removed externally: {dst_path.name}")
                    break

                time.sleep(1)
