import os
from pathlib import Path
from typing import Set
import json
from .utils import serialize_object, deep_merge

class Config:
    def __init__(self, with_env=True, import_config=None):
        self.general = {
            "api_url": "https://api.put.io/v2",
            "log_level": "INFO",
            "daemon": False,
        }
        self.auth = {
            "oauth_token": "",
        }
        self.paths = {
            "target": Path("/target"),
            "map_str": "",
            "sync_mappings": {},
        }
        self.permissions = {
            "target_uid": 1000,
            "target_gid": 1000,
            "target_dmode": 0o755,
            "target_fmode": 0o755,
        }
        self.behavior = {
            "action": "copy",  # copy or move
            "guessit": True,
            "skip_existing": False,
            "empty_trash": False,
            "poll_interval": 300,
        }
        self.download = {
            "filetypes_str": "",
            "allowed_extensions": set(),
            "max_segments": 8,
            "min_segment_size": "50MB",
            "min_segment_size_bytes": 0,
            "max_concurrent": 3,
        }
        self.mirrors = {
            "enabled": False,
            "min_speed": "",
            "min_speed_bytes": 0,
            "benchmark_only": False,
            "benchmark_file": Path("mirror_speeds.json"),
            "map": {
                "Montreal": "bhs1",
                "New_York": "ny1",
                "Los_Angeles": "la1",
                "Utah": "utah1",
                "Washington_D.C.": "vin1",
                "Oregon": "hil1",
                "London": "lon3",
                "cdn77": "s100-cdn77",
                "Amsterdam": "s100"
            }
        }

        if import_config:
            self.import_config(import_config)

        if with_env:
            self.load_from_env()


    def import_config(self, config_file: str):
        """Imports config from a json file."""
        import_path = Path(config_file)
        if import_path.exists():
            with open(import_path, 'r') as f:
                imported_data = json.load(f)

            for key, values in imported_data.items():
                if hasattr(self, key):
                    base_dict = getattr(self, key)
                    merged = deep_merge(base_dict, values)
                    setattr(self, key, merged)

            # Convert json objects back to appropriate types
            if isinstance(self.paths.get('target'), str):
                self.paths['target'] = Path(self.paths['target'])

            if isinstance(self.paths.get('sync_mappings'), dict):
                for key, value in self.paths['sync_mappings'].items():
                    if isinstance(value, str):
                        self.paths['sync_mappings'][key] = Path(value)
            
            for key in ['target_dmode', 'target_fmode']:
                val = self.permissions.get(key)
                if isinstance(val, str):
                    self.permissions[key] = int(val, 8) if val.startswith('0o') else int(val)

            if isinstance(self.download['allowed_extensions'], list):
                self.download['allowed_extensions'] = set(self.download['allowed_extensions'])

            if isinstance(self.mirrors.get('benchmark_file'), str):
                self.mirrors['benchmark_file'] = Path(self.mirrors['benchmark_file'])

        else:
            log.error(f"Config file not found: {config_file}")


    def load_from_env(self):
        """Load config from environment variables."""
        # General
        self.general['log_level'] = os.environ.get('LOG_LEVEL', self.general['log_level']).upper()

        # Auth
        self.auth['oauth_token'] = os.environ.get('PUTIO_OAUTH_TOKEN', self.auth['oauth_token'])

        # Load secrets from file if needed
        if not self.auth['oauth_token'] and os.environ.get('PUTIO_OAUTH_TOKEN_FILE'):
            try:
                with open(os.environ['PUTIO_OAUTH_TOKEN_FILE'], 'r') as f:
                    self.auth['oauth_token'] = f.read().strip()
            except Exception: pass

        # Paths
        self.paths['target'] = Path(os.environ.get('PUTIO_TARGET', str(self.paths['target'])))
        self.paths['map_str'] = os.environ.get('PUTIO_DIRECTORY_MAP', self.paths['map_str'])

        # Permissions
        self.permissions['target_uid'] = int(os.environ.get('PUTIO_TARGET_UID', self.permissions['target_uid']))
        self.permissions['target_gid'] = int(os.environ.get('PUTIO_TARGET_GID', self.permissions['target_gid']))
        self.permissions['target_dmode'] = int(os.environ.get('PUTIO_TARGET_DMODE', '755'), 8)
        self.permissions['target_fmode'] = int(os.environ.get('PUTIO_TARGET_FMODE', '755'), 8)

        # Behavior
        self.behavior['action'] = os.environ.get('PUTIO_SYNC_ACTION', self.behavior['action']).lower()
        self.behavior['guessit'] = os.environ.get('PUTIO_GUESSIT', str(self.behavior['guessit'])).lower() == 'true'
        self.behavior['skip_existing'] = os.environ.get('PUTIO_SKIP_EXISTING', str(self.behavior['skip_existing'])).lower() == 'true'
        self.behavior['empty_trash'] = os.environ.get('PUTIO_EMPTY_TRASH', str(self.behavior['empty_trash'])).lower() == 'true'
        self.behavior['poll_interval'] = int(os.environ.get('PUTIO_POLL_INTERVAL_SECONDS', self.behavior['poll_interval']))

        # Download
        self.download['filetypes_str'] = os.environ.get('PUTIO_FILETYPES', self.download['filetypes_str'])
        self.download['max_segments'] = int(os.environ.get('PUTIO_MAX_SEGMENTS', self.download['max_segments']))
        self.download['min_segment_size'] = os.environ.get('PUTIO_MIN_SEGMENT_SIZE', self.download['min_segment_size'])
        self.download['max_concurrent'] = int(os.environ.get('PUTIO_MAX_CONCURRENT_DOWNLOADS', self.download['max_concurrent']))

        # Mirrors
        self.mirrors['enabled'] = os.environ.get('PUTIO_ENABLE_MIRRORS', str(self.mirrors['enabled'])).lower() == 'true'
        self.mirrors['min_speed'] = os.environ.get('PUTIO_MIN_MIRROR_SPEED', self.mirrors['min_speed'])
        self.mirrors['benchmark_only'] = os.environ.get('PUTIO_BENCHMARK_ONLY', str(self.mirrors['benchmark_only'])).lower() == 'true'
        self.mirrors['benchmark_file'] = Path(os.environ.get('PUTIO_BENCHMARK_FILE', str(self.mirrors['benchmark_file'])))


    def parse_calculated_values(self):
        """Parse calculated values from the config."""
        # Extensions
        _default_exts = {
            'mkv', 'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm', # Video
            'srt', 'sub', 'sbv', 'vtt', 'ass', # Subtitles
            'mp3', 'flac', 'aac', 'wav', 'm4a', 'ogg' # Audio
        }
        if self.download['filetypes_str']:
            self.download['allowed_extensions'] = {f".{ext.strip().lstrip('.').lower()}" for ext in self.download['filetypes_str'].split(',')}
        elif not self.download['allowed_extensions']:
            self.download['allowed_extensions'] = {f".{ext}" for ext in _default_exts}

        # Parse Sizes
        if self.download['min_segment_size'] and not self.download['min_segment_size_bytes']:
            self.download['min_segment_size_bytes'] = self._parse_size(self.download['min_segment_size'])

        if self.mirrors['min_speed'] and not self.mirrors['min_speed_bytes']:
            val = self.mirrors['min_speed'].strip()
            if val.lower().endswith('/s'): val = val[:-2]
            self.mirrors['min_speed_bytes'] = self._parse_size(val)

        # Parse Map
        if self.paths['map_str'] and not self.paths['sync_mappings']:
            self._parse_sync_map()


    def _parse_size(self, size_str: str) -> int:
        """Parse a size string into bytes."""
        size_str = size_str.upper()
        if size_str.endswith('MB'):
            return int(float(size_str[:-2]) * 1024 * 1024)
        if size_str.endswith('GB'):
            return int(float(size_str[:-2]) * 1024 * 1024 * 1024)
        if size_str.endswith('KB'):
            return int(float(size_str[:-2]) * 1024)
        try:
            return int(size_str)
        except:
            return 0


    def _parse_sync_map(self):
        """Parse the sync map string into a dictionary."""
        if not self.paths['map_str']: return
        pairs = self.paths['map_str'].split(',')

        for pair in pairs:
            if ':' not in pair: continue
            source_str, target_str = pair.split(':', 1)
            source = Path(source_str.strip().strip('/\\'))
            target = Path(target_str.strip().strip('/\\'))
            self.paths['sync_mappings'][source] = target


    def get_config(self):
        """Returns the config dictionary."""
        cfg = {
            "general": self.general,
            "auth": self.auth,
            "paths": self.paths,
            "permissions": self.permissions,
            "behavior": self.behavior,
            "download": self.download,
            "mirrors": self.mirrors
        }

        return cfg

    def dump_config(self, sections=None):
        """Outputs config in json format. Accepts an optional list of sections, or it will print all sections."""
        serialized_cfg = serialize_object(self.get_config())

        output_cfg = {}
        if sections and 'all' not in sections:
            for s in sections:
                if s in serialized_cfg:
                    output_cfg[s] = serialized_cfg[s]
        else:
            output_cfg = serialized_cfg

        return json.dumps(output_cfg, indent=4)
