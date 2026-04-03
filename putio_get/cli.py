import argparse
import signal
import sys
from importlib.metadata import version
from rich_argparse import RichHelpFormatter
from .config import Config
from .core import Application, console
from .utils import setup_logging

__version__ = version('putio-get')


def get_parser():
    parser = argparse.ArgumentParser(description=f"putio-get sync tool v{__version__}", formatter_class=RichHelpFormatter)

    # General
    parser.add_argument('--version', '-v', action='version', version=f'%(prog)s {__version__}')
    parser.add_argument('--log-level', type=str.upper, choices=['TRACE', 'DEBUG', 'INFO', 'WARNING', 'ERROR'], help='Log level')
    parser.add_argument('--daemon', '-d', action='store_true', help='Run in daemon mode (looping)')
    parser.add_argument('--config-file', type=str, default=None, help='Load config from the specified json file. Overridden by env vars then args')
    parser.add_argument('--print-config', type=str, default=None, nargs='?', const='all', help='Print config and exit, optionally specify sections to print (e.g. "general,auth,paths") Any additional arguments/commands are ignored')

    # Auth
    parser.add_argument('--oauth-token', type=str, help='Put.io OAuth Token')

    # Paths
    parser.add_argument('--target', type=str, help='Target directory')
    parser.add_argument('--map', type=str, help='Sync map (source:target pairs)')

    # Permissions
    parser.add_argument('--target-uid', type=int, help='Target UID')
    parser.add_argument('--target-gid', type=int, help='Target GID')
    parser.add_argument('--target-dmode', type=str, help='Target directory mode')
    parser.add_argument('--target-fmode', type=str, help='Target file mode')

    # Behavior
    parser.add_argument('--action', type=str, choices=['copy', 'move'], help='Sync action')
    parser.add_argument('--guessit', action='store_true', help='Rename files using guessit')
    parser.add_argument('--skip-existing', action='store_true', help='Skip files present at startup')
    parser.add_argument('--empty-trash', action='store_true', help='Empty trash after move')
    parser.add_argument('--poll-interval', type=int, help='Seconds between polls')

    # Download
    parser.add_argument('--filetypes', type=str, help='Allowed extensions')
    parser.add_argument('--max-segments', type=int, help='Max connections per download')
    parser.add_argument('--min-segment-size', type=str, help='Min segment size')
    parser.add_argument('--max-concurrent-downloads', type=int, help='Max global concurrent downloads')

    # Mirrors
    parser.add_argument('--enable-mirrors', action='store_true', help='Enable mirrors')
    parser.add_argument('--min-mirror-speed', type=str, help='Min mirror speed')
    parser.add_argument('--benchmark-file', type=str, help='Benchmark json file')
    parser.add_argument('--benchmark-only', action='store_true', help='Run benchmark and exit')

    return parser


def main():
    parser = get_parser()
    args = parser.parse_args()

    # Load config file if specified, otherwise load defautls.
    # Env vars override both config file and defaults.
    if args.config_file:
        cfg = Config(with_env=True, import_config=args.config_file)
    else:
        cfg = Config(with_env=True)

    # Override with args if present
    # General
    if args.log_level: cfg.general['log_level'] = args.log_level
    if args.daemon: cfg.general['daemon'] = args.daemon

    # Auth
    if args.oauth_token: cfg.auth['oauth_token'] = args.oauth_token

    # Paths
    if args.target: cfg.paths['target'] = Path(args.target)
    if args.map: cfg.paths['map_str'] = args.map

    # Permissions
    if args.target_uid: cfg.permissions['target_uid'] = args.target_uid
    if args.target_gid: cfg.permissions['target_gid'] = args.target_gid
    if args.target_dmode: cfg.permissions['target_dmode'] = args.target_dmode
    if args.target_fmode: cfg.permissions['target_fmode'] = args.target_fmode

    # Behavior
    if args.action: cfg.behavior['action'] = args.action
    if args.guessit: cfg.behavior['guessit'] = True
    if args.skip_existing: cfg.behavior['skip_existing'] = True
    if args.empty_trash: cfg.behavior['empty_trash'] = True
    if args.poll_interval: cfg.behavior['poll_interval'] = args.poll_interval

    # Download
    if args.filetypes: cfg.download['filetypes_str'] = args.filetypes
    if args.max_segments: cfg.download['max_segments'] = args.max_segments
    if args.min_segment_size: cfg.download['min_segment_size'] = args.min_segment_size
    if args.max_concurrent_downloads: cfg.download['max_concurrent'] = args.max_concurrent_downloads

    # Mirrors
    if args.enable_mirrors: cfg.mirrors['enabled'] = True
    if args.min_mirror_speed: cfg.mirrors['min_speed'] = args.min_mirror_speed
    if args.benchmark_file: cfg.mirrors['benchmark_file'] = args.benchmark_file
    if args.benchmark_only: cfg.mirrors['benchmark_only'] = True

    # Parse calculated values since they may have changed from args
    cfg.parse_calculated_values()

    if args.print_config:
        print(cfg.dump_config([s.strip() for s in args.print_config.split(',')]))
        sys.exit(0)

    setup_logging(cfg.general['log_level'])

    if not cfg.auth['oauth_token']:
        print("Error: PUTIO_OAUTH_TOKEN is required.")
        sys.exit(1)

    app = Application(cfg)

    def signal_handler(signum, frame):
        sig_name = signal.Signals(signum).name
        console.print(f"\n[bold red]{sig_name}[/bold red] received. Stopping...")
        app.shutdown()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    app.start()


if __name__ == "__main__":
    main()
