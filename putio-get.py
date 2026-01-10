#!/usr/bin/env python3

import os
import sys
import time
import shutil
import time
import signal
import threading
from pathlib import Path
import argparse
from rich_argparse import RichHelpFormatter
from guessit import guessit
import logging
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
    DownloadColumn
)
from rich.traceback import install


# --- Argparse for CLI Arguments ---
def get_args():
    parser = argparse.ArgumentParser(description="putio-get sync script", formatter_class=RichHelpFormatter)
    parser.add_argument('--mountpoint', type=str, default=os.environ.get('DAV_MOUNT', '/dav'), help='DAV mountpoint')
    parser.add_argument('--target', type=str, default=os.environ.get('PUTIO_TARGET', '/target'), help='Target directory')
    parser.add_argument('--map', type=str, default=os.environ.get('DAV_MAP', ''), help='Sync map (source:target pairs)')
    parser.add_argument('--action', type=str, choices=['copy', 'move'], default=os.environ.get('PUTIO_SYNC_ACTION', 'copy').lower(), help='Sync action: copy or move')
    parser.add_argument('--guessit', action='store_true', default=os.environ.get('PUTIO_GUESSIT', 'false').lower() == 'true', help='Rename files to match their metadata (default: False)')
    parser.add_argument('--skip-existing', action='store_true', default=os.environ.get('PUTIO_SKIP_EXISTING', 'false').lower() == 'true', help='Skip existing files in source (default: False) when the loop starts')
    parser.add_argument('--poll-interval', type=int, default=int(os.environ.get('PUTIO_POLL_INTERVAL_SECONDS', 300)), help='Polling interval in seconds')
    parser.add_argument('--filetypes', type=str, default=os.environ.get('PUTIO_FILETYPES', ''), help='Comma-separated list of allowed file extensions (e.g., mkv,mp4)')
    parser.add_argument('--log-level', type=str.upper, choices=['TRACE', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], default=os.environ.get('LOG_LEVEL', 'INFO').upper(), help='Logging level')
    return parser.parse_args()

# --- Configuration from Arguments/Environment Variables ---
args = get_args()
DAV_MOUNT = Path(args.mountpoint)
PUTIO_TARGET = Path(args.target)
PUTIO_POLL_INTERVAL_SECONDS = args.poll_interval
PUTIO_SYNC_ACTION = args.action
DAV_MAP = args.map
PUTIO_GUESSIT = args.guessit
PUTIO_SKIP_EXISTING = args.skip_existing
LOG_LEVEL = args.log_level

# Configure Logging and output
lib_loggers = ["guessit", "rebulk"]
install(show_locals=True, suppress=[lib_loggers])
console = Console()

## Add TRACE level
logging.addLevelName(5, "TRACE")
logging.TRACE = 5

def trace(self, message, *args, **kwargs):
    if self.isEnabledFor(5):
        self._log(5, message, args, **kwargs)

logging.Logger.trace = trace

## Configure Library Logging
class TraceLabelFilter(logging.Filter):
    def filter(self, record):
        # Relabels DEBUG logs from libraries to TRACE level name for visual distinction
        if record.levelno == logging.DEBUG and record.name.startswith(tuple(lib_loggers)):
            record.levelname = "TRACE"
            record.levelno = 5
        return True

rich_handler = RichHandler(rich_tracebacks=True, markup=True)
if LOG_LEVEL == "TRACE":
    rich_handler.addFilter(TraceLabelFilter())
    for lib in lib_loggers:
        logging.getLogger(lib).setLevel(logging.DEBUG)
else:
    for lib in lib_loggers:
        logging.getLogger(lib).setLevel(logging.INFO)

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[rich_handler]
)
log = logging.getLogger("rich")


# Processing Filetypes
_default_exts = {
    # Video
    'mkv', 'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm',
    # Subtitle
    'srt', 'sub', 'sbv', 'vtt', 'ass',
    # Audio
    'mp3', 'flac', 'aac', 'wav', 'm4a', 'ogg'
}

if args.filetypes:
    # Normalize user input to ensure they start with '.'
    ALLOWED_EXTENSIONS = {f".{ext.strip().lstrip('.').lower()}" for ext in args.filetypes.split(',')}
else:
    ALLOWED_EXTENSIONS = {f".{ext}" for ext in _default_exts}

log.debug(f"Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

DAV_UID = int(os.environ.get('DAV_UID', 1000))
DAV_GID = int(os.environ.get('DAV_GID', 1000))
# Modes are read as octal strings (e.g., '755') and converted to integers
DAV_DMODE = int(os.environ.get('DAV_DMODE', '755'), 8)
DAV_FMODE = int(os.environ.get('DAV_FMODE', '755'), 8)
# -----------------------------------------------

# --- Graceful Shutdown Event ---
exit_event = threading.Event()


def signal_handler(signum, frame):
    """Signal handler that sets the exit_event when a signal is received."""
    signal_name = signal.Signals(signum).name
    console.print(f"\nSignal [bold red]{signal_name}[/bold red] ([bold yellow]{signum}[/bold yellow]) received. Shutting down gracefully...")
    console.print("Cancelling any active file operations. Please wait.")
    exit_event.set()


def apply_permissions(path: Path, is_file: bool):
    """Applies configured ownership and permissions to a path."""
    mode = DAV_FMODE if is_file else DAV_DMODE
    try:
        os.chmod(path, mode)
        # os.chown is not available on Windows, so we check for it
        if hasattr(os, 'chown'):
            os.chown(path, DAV_UID, DAV_GID)
    except Exception as e:
        log.warning(f"Could not set permissions on {str(path)}: {e}")


def parse_sync_map(sync_map_str: str) -> dict[Path, Path]:
    """
    Parses the DAV_MAP environment variable string into a dictionary.
    """
    mappings = {}
    if not sync_map_str:
        log.warning("No sync map provided. Skipping sync map parsing.")
        return mappings

    pairs = sync_map_str.split(',')
    for pair in pairs:
        if ':' not in pair:
            log.warning(f"Invalid mapping pair, skipping: {pair}")
            continue
        source_str, target_str = pair.split(':', 1)
        source = Path(source_str.strip().strip('/\\'))
        target = Path(target_str.strip().strip('/\\'))
        mappings[source] = target
    return mappings


def get_current_paths(directory: Path, mappings: dict[Path, Path]) -> set[Path]:
    """
    Recursively walks and returns a set of all file/directory paths.
    If mappings are provided, only the mapped source directories are scanned.
    """
    if not directory.is_dir():
        return set()

    if not mappings:
        return {p for p in directory.glob('**/*')}

    all_paths = set()
    for source_map in mappings.keys():
        scan_dir = directory / source_map
        if scan_dir.is_dir():
            all_paths.update(p for p in scan_dir.glob('**/*'))
            all_paths.add(scan_dir)
    return all_paths


def copy_with_progress(src_path: Path, dst_path: Path):
    """Copies a file from src_path to dst_path and displays a progress bar."""
    if PUTIO_SYNC_ACTION == 'move':
        action = 'Moving'
    elif PUTIO_SYNC_ACTION == 'copy':
        action = 'Copying'
    else:
        log.error(f"Invalid sync action: {PUTIO_SYNC_ACTION}")
        return

    total_size = src_path.stat().st_size
    desc = f"{action}: {dst_path.name}"
    
    progress = Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        transient=True,
        refresh_per_second=1
    )

    try:
        with progress:
            task = progress.add_task(desc, total=total_size)
            with open(src_path, 'rb') as fsrc, open(dst_path, 'wb') as fdst:
                bytes_copied = 0
                while not exit_event.is_set():
                    buf = fsrc.read(1024 * 1024)
                    if not buf:
                        break
                    fdst.write(buf)
                    bytes_copied += len(buf)
                    progress.update(task, completed=bytes_copied)
        
        if not exit_event.is_set():
            shutil.copystat(src_path, dst_path)
            apply_permissions(dst_path, is_file=True)
            
    finally:
        if exit_event.is_set():
            log.warning(f"Copy cancelled. Cleaning up partial file: {str(dst_path)}")
            dst_path.unlink(missing_ok=True)


def move_with_progress(src_path: Path, dst_path: Path):
    """Moves a file from src_path to dst_path, cancellable via exit_event."""
    try:
        # Atomic rename is fast but may not work across different filesystems.
        os.rename(src_path, dst_path)
        # Apply permissions after rename to ensure they match env vars
        apply_permissions(dst_path, is_file=True)
    except OSError:
        # Fallback for cross-device moves
        console.print(f"  -> Performing cross-device move...")
        copy_with_progress(src_path, dst_path)
        if not exit_event.is_set():
            os.remove(src_path)

def get_dest_path(base_path: Path, sub_path: Path):
    log.debug(f"Getting Destination Path: {str(sub_path)}")
    if PUTIO_GUESSIT:
        guess = dict(guessit(str(sub_path)))
        guess_str = str(guess)
        log.debug(f"Guessit: {guess_str}")
        dest_path = base_path
        if guess['type'] == 'episode':
            series_path = f"{guess['title']} ({guess['year']})" if 'year' in guess else guess['title']
            dest_path = Path(dest_path, series_path)
            dest_path = Path(dest_path, f"Season {str(guess['season']).zfill(2)}")
            episode_filename = f"{guess['title']} - S{str(guess['season']).zfill(2)}E{str(guess['episode']).zfill(2)}"
            if 'episode_title' in guess:
                episode_filename += f" - {guess['episode_title']}"
            if 'subtitle_language' in guess:
                episode_filename += f".{guess['subtitle_language'][:2].lower()}"
            episode_filename += f".{guess['container']}"
            dest_path = Path(dest_path, episode_filename)
        elif guess['type'] == 'movie':
            movie_filename = f"{guess['title']} ({guess['year']})" if 'year' in guess else guess['title']
            if 'subtitle_language' in guess:
                movie_filename += f".{guess['subtitle_language'][:2].lower()}"
            movie_filename += f".{guess['container']}"
            dest_path = Path(dest_path, movie_filename)
        else:
            dest_path = sub_path
    else:
        dest_path = sub_path
    
    dest_path = Path(base_path, dest_path)
    dest_path = Path(base_path, dest_path)
    log.debug(f"Setting Destination Path{(' (Guessit)' if PUTIO_GUESSIT else '')}: {str(dest_path)}")
    return dest_path


def process_paths(paths, sync_mappings, label):
    """Process a set of paths (existing or new) according to sync settings."""
    moved_items = set()
    if paths:
        console.print(f"\n[blue][bold]---[/bold] {label} [bold]---[/blue]")
        for path in sorted(list(paths), key=lambda p: len(p.parts)):
            if exit_event.is_set(): break
            
            log.debug(f"Examining: {str(path)}")

            # We only process files. Directories are created on demand.
            if not path.is_file():
                log.debug(f"Skipping directory (files only): {str(path)}")
                continue

            # Filter by extension
            if path.suffix.lower() not in ALLOWED_EXTENSIONS:
                log.debug(f"Skipping file (extension '{str(path.suffix.lower())}' not allowed): {str(path)}")
                continue

            relative_path = path.relative_to(DAV_MOUNT)
            destination_path = None
            if sync_mappings:
                for source_map, target_map in sync_mappings.items():
                    try:
                        sub_path = relative_path.relative_to(source_map)
                        destination_path = get_dest_path(PUTIO_TARGET / target_map, sub_path)
                        break
                    except ValueError:
                        continue
            else:
                destination_path = get_dest_path(PUTIO_TARGET, relative_path)
            
            if destination_path is None:
                continue

            try:
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                parent_dir = destination_path.parent
                while parent_dir != PUTIO_TARGET.parent and (parent_dir.is_relative_to(PUTIO_TARGET) or parent_dir == PUTIO_TARGET):
                    apply_permissions(parent_dir, is_file=False)
                    if parent_dir == PUTIO_TARGET:
                        break
                    parent_dir = parent_dir.parent
                
                log.info(f"Found: {str(path)}")
                if PUTIO_SYNC_ACTION == "copy":
                    copy_with_progress(path, destination_path)
                elif PUTIO_SYNC_ACTION == "move":
                    move_with_progress(path, destination_path)
                    if not exit_event.is_set(): moved_items.add(path)
                
                if not exit_event.is_set():
                    log.info(f"Action complete for: {str(destination_path)}")

            except FileNotFoundError:
                log.warning(f"File '{str(path)}' was deleted before it could be processed.")
            except Exception as e:
                log.error(f"Could not process '{str(path)}': {e}")
    return moved_items

def main():
    """Main function to run the directory monitoring loop."""
    # --- Register Signal Handlers ---
    signals_to_handle = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, 'SIGHUP'): signals_to_handle.append(signal.SIGHUP)
    if hasattr(signal, 'SIGQUIT'): signals_to_handle.append(signal.SIGQUIT)
    for sig in signals_to_handle:
        signal.signal(sig, signal_handler)

    sync_mappings = parse_sync_map(DAV_MAP)

    console.print("\n[blue][bold]---[/bold] Directory Monitor Started [bold]---[/bold][/blue]")
    if sync_mappings:
        console.print("Sync mappings are defined:")
        for src, dest in sync_mappings.items():
            console.print(f"  - From: {DAV_MOUNT / src}")
            console.print(f"    To:   {PUTIO_TARGET / dest}")
    else:
        console.print("No sync mappings defined. Monitoring entire source directory.")

    console.print(f"Source Directory: {DAV_MOUNT}")
    console.print(f"Target Directory: {PUTIO_TARGET}")
    console.print(f"Action on New Files: {PUTIO_SYNC_ACTION.upper()}")
    console.print("\n[yellow]Press Ctrl+C to stop.[/yellow]\n")

    # --- Initial Setup ---
    if not DAV_MOUNT.is_dir():
        log.error(f"Source directory '{DAV_MOUNT}' does not exist. Exiting.")
        return
    PUTIO_TARGET.mkdir(parents=True, exist_ok=True)
    apply_permissions(PUTIO_TARGET, is_file=False)

    known_paths = get_current_paths(DAV_MOUNT, sync_mappings)
    log.info(f"Initial scan complete. Found {len(known_paths)} files and directories.")

    # --- Handle Existing Files at Startup ---
    if not PUTIO_SKIP_EXISTING:
        moved_items = process_paths(known_paths, sync_mappings, "Processing Existing Items")
        known_paths = known_paths - moved_items

    # --- Monitoring Loop ---
    try:
        while not exit_event.is_set():
            exit_event.wait(PUTIO_POLL_INTERVAL_SECONDS)
            if exit_event.is_set(): break

            current_paths = get_current_paths(DAV_MOUNT, sync_mappings)
            new_paths = current_paths - known_paths
            moved_items = process_paths(new_paths, sync_mappings, "Detected New Items")

            if exit_event.is_set(): break

            removed_paths = known_paths - current_paths
            if removed_paths:
                log.debug("\n--- Detected Removed Items ---")
                for path in removed_paths:
                    log.debug(f"  [bold red][REMOVED][/bold red] {str(path)}")

            known_paths = current_paths - moved_items

    except Exception as e:
        log.critical(f"\nAn unexpected error occurred: {e}")
    finally:
        console.print("\n[blue][bold]---[/bold] Directory Monitor Stopped [bold]---[/bold][/blue]")

if __name__ == "__main__":
    main()

