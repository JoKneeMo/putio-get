import os
import hashlib
import logging
import json
from pathlib import Path
from rich.console import Console
from rich.logging import RichHandler
from rich.traceback import install

# Configure Logging and output
lib_loggers = ["guessit", "rebulk", "httpx", "httpcore"]
install(show_locals=True, suppress=lib_loggers)
console = Console()

# Add TRACE level
logging.addLevelName(5, "TRACE")
logging.TRACE = 5


def trace(self, message, *args, **kwargs):
    if self.isEnabledFor(5):
        self._log(5, message, args, **kwargs)


logging.Logger.trace = trace


# Configure Library Logging
class TraceLabelFilter(logging.Filter):
    def filter(self, record):
        # Relabels DEBUG logs from libraries to TRACE level name for visual distinction
        if record.levelno == logging.DEBUG and record.name.startswith(tuple(lib_loggers)):
            record.levelname = "TRACE"
            record.levelno = 5
        return True


def setup_logging(log_level: str):
    show_path = log_level in ("TRACE", "DEBUG")
    rich_handler = RichHandler(rich_tracebacks=True, markup=True, show_path=show_path)
    if log_level == "TRACE":
        rich_handler.addFilter(TraceLabelFilter())
        for lib in lib_loggers:
            logging.getLogger(lib).setLevel(logging.DEBUG)
    else:
        for lib in lib_loggers:
            logging.getLogger(lib).setLevel(logging.WARNING)

    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[rich_handler],
        force=True
    )


log = logging.getLogger("rich")


def apply_permissions(path: Path, is_file: bool, uid: int, gid: int, fmode: int, dmode: int):
    """Applies configured ownership and permissions to a path."""
    mode = fmode if is_file else dmode
    try:
        os.chmod(path, mode)
        # os.chown is not available on Windows
        if hasattr(os, 'chown'):
            os.chown(path, uid, gid)
    except Exception as e:
        log.warning(f"Could not set permissions on {str(path)}: {e}")


def verify_sha1(path: Path, expected_sha1: str) -> bool:
    """Verifies the SHA-1 checksum of a local file."""
    try:
        h = hashlib.sha1()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest().lower() == expected_sha1.lower()
    except Exception as e:
        log.error(f"Error checking local SHA-1: {e}")
        return False


def serialize_object(obj):
    """Helper to convert non-serializable objects to JSON-friendly types."""
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (set, tuple)):
        return [serialize_object(i) for i in obj]
    if isinstance(obj, dict):
        return {str(k): serialize_object(v) for k, v in obj.items()}
    try:
        json.dumps(obj)
        return obj
    except (TypeError, OverflowError):
        return str(obj)


def deep_merge(base, overrides):
    """Recursively merges overrides into base dictionary."""
    for key, value in overrides.items():
        if isinstance(value, dict) and key in base and isinstance(base[key], dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base