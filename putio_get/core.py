import logging
import threading
from pathlib import Path
from typing import Set, Dict, List, Optional

from guessit import guessit
from rich.console import Console

from .config import Config
from .downloader import Downloader
from .client import PutioClient
from .utils import apply_permissions, verify_sha1

log = logging.getLogger("rich")
console = Console()


class Application:
    def __init__(self, config: Config):
        self.config = config
        self.exit_event = threading.Event()
        self.downloader = None
        self.client = None
        self.known_files = {}  # id -> file_obj

    def start(self):
        # Benchmark
        if self.config.mirrors['enabled'] or self.config.mirrors['benchmark_only']:
            from .mirrors import get_mirror_rankings
            self.sorted_mirrors = get_mirror_rankings(self.config)
            if self.config.mirrors['benchmark_only']:
                console.print("\n[bold green]Benchmark Complete.[/bold green]")
                for m in self.sorted_mirrors:
                    console.print(f"  {m['name']}: {m['speed']/1024/1024:.2f} MB/s")
                return
        else:
            self.sorted_mirrors = None

        # Init Client
        self.client = PutioClient(self.config)
        try:
            self.client.list_files()
            log.info("Connected to Put.io API successfully.")
        except Exception as e:
            log.critical(f"Failed to connect to Put.io API: {e}")
            return

        # Init Downloader
        self.downloader = Downloader(self.config, self.sorted_mirrors)

        self._ensure_dir(self.config.paths['target'])
        console.print(f"Target Directory: {self.config.paths['target']}")

        # Initial Scan
        self.known_files = self._scan_files()
        log.info(f"Initial scan complete. Found {len(self.known_files)} items.")

        if not self.config.behavior['skip_existing']:
            self._process_files(self.known_files, "Processing Existing Items")

        if self.config.general['daemon']:
            self._run_daemon()
        else:
            log.info("Single run is now complete.")

    def shutdown(self):
        log.info("Shutting down application...")
        self.exit_event.set()

    def _ensure_dir(self, path: Path):
        base = self.config.paths['target']
        path = path if path.is_absolute() else base / path

        if not path.is_relative_to(base):
            raise ValueError("Path escapes target")

        current = base
        for part in path.relative_to(base).parts:
            current /= part
            if not current.exists():
                log.info(f"Creating Directory: {str(current)}")
                current.mkdir()
                apply_permissions(current, False,
                    self.config.permissions['target_uid'],
                    self.config.permissions['target_gid'],
                    self.config.permissions['target_fmode'],
                    self.config.permissions['target_dmode'])

    def _scan_files(self) -> Dict[str, Dict]:
        """
        Returns a dictionary of file_id -> file_object
        Also resolves full paths for files.
        """
        all_items = self.client.list_files()

        id_map = {item['id']: item for item in all_items}

        def get_path(item_id):
            item = id_map.get(item_id)
            if not item: return Path("/")
            if item.get('parent_id') and item['parent_id'] > 0:
                return get_path(item['parent_id']) / item['name']
            return Path("/") / item['name']

        results = {}
        for item in all_items:
            if item['file_type'] == 'FOLDER': continue

            full_path = get_path(item['id'])

            ext = "." + item['name'].split('.')[-1].lower() if '.' in item['name'] else ""
            if ext not in self.config.download['allowed_extensions']:
                continue

            target_root = self.config.paths['target']
            rel_path = None

            if self.config.paths['sync_mappings']:
                matched_map = False
                for src_map, tgt_map in self.config.paths['sync_mappings'].items():
                    src_path_obj = Path("/") / src_map
                    if full_path.is_relative_to(src_path_obj):
                        rel = full_path.relative_to(src_path_obj)
                        target_root = self.config.paths['target'] / tgt_map
                        rel_path = rel
                        matched_map = True
                        break

                if not matched_map:
                    continue
            else:
                rel_path = full_path.relative_to("/")

            item['rel_path'] = rel_path
            item['target_root'] = target_root
            results[str(item['id'])] = item

        return results

    def _format_title_with_year(self, guess: dict) -> str:
        return f"{guess['title']} ({guess['year']})" if 'year' in guess else guess['title']

    def _format_sub_lang_suffix(self, guess: dict) -> str:
        if 'subtitle_language' in guess:
            lang = str(guess['subtitle_language'])
            return f".{lang[:2].lower()}"
        return ""

    def _get_dest_path(self, item_path: Path) -> Path:
        if not self.config.behavior['guessit']:
            return Path(item_path)

        try:
            guess = dict(guessit(str(item_path)))

            media_type = guess.get('type')
            container = guess.get('container')

            if media_type == 'episode':
                title = guess['title']
                season_num = str(guess.get('season')).zfill(2)
                episode_num = str(guess.get('episode')).zfill(2)

                show_dir = self._format_title_with_year(guess)
                season_dir = f"Season {season_num}"

                ep_name = f"{title} - S{season_num}E{episode_num}"
                if 'episode_title' in guess:
                    ep_name += f" - {guess['episode_title']}"
                ep_name += self._format_sub_lang_suffix(guess)
                ep_name += f".{container}"

                return Path(show_dir, season_dir, ep_name)

            if media_type == 'movie':
                movie = self._format_title_with_year(guess)
                movie += self._format_sub_lang_suffix(guess)
                movie += f".{container}"
                return Path(movie)

        except Exception:
            pass

        return Path(item_path)

    def _process_files(self, files: Dict[str, Dict], label: str):
        if not files: return
        console.print(f"\n[blue][bold]---[/bold] {label} [bold]---[/blue]")

        # Sort by path
        sorted_files = sorted(files.values(), key=lambda x: str(x['rel_path']))

        processed_ids = []

        for item in sorted_files:
            if self.exit_event.is_set(): break

            try:
                item_path = self._get_dest_path(item['rel_path'])
                dest_path = item['target_root'].joinpath(item_path)
                self._ensure_dir(dest_path.parent)

                url = self.client.get_file_url(item['id'])
                if not url:
                    log.error(f"Could not get download URL for {item['name']}")
                    continue

                file_size = item['size']
                sha1 = item.get('sha1')

                success = False
                if dest_path.exists() and sha1:
                    log.info(f"File {dest_path.name} exists, verifying existing SHA-1...")
                    if verify_sha1(dest_path, sha1):
                        log.info(f"SHA-1 match for {dest_path.name}. Skipping download.")
                        success = True

                if not success:
                    success = self.downloader.download(url, dest_path, file_size, self.exit_event, sha1)

                if success:
                    apply_permissions(dest_path, True,
                        self.config.permissions['target_uid'],
                        self.config.permissions['target_gid'],
                        self.config.permissions['target_fmode'],
                        self.config.permissions['target_dmode'])

                    if self.config.behavior['action'] == 'move':
                        processed_ids.append(item['id'])

            except Exception as e:
                log.error(f"Error processing {item.get('name')}: {e}")

        # Cleanup
        if processed_ids:
            self.client.delete_files(processed_ids)
            if self.config.behavior['empty_trash']:
                self.client.empty_trash()

    def _run_daemon(self):
        console.print("\n[blue][bold]---[/bold] Daemon Started [bold]---[/bold][/blue]")
        while not self.exit_event.is_set():
            self.exit_event.wait(self.config.behavior['poll_interval'])
            if self.exit_event.is_set(): break

            try:
                current = self._scan_files()
                new_ids = set(current.keys()) - set(self.known_files.keys())
                if new_ids:
                    new_items = {k: current[k] for k in new_ids}
                    self._process_files(new_items, "Detected New Files")

                self.known_files = current
            except Exception as e:
                log.error(f"Daemon error: {e}")
