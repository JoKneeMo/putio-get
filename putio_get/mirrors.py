import time
import json
import logging
import httpx
from .config import Config

log = logging.getLogger("rich")


def benchmark_mirror(name: str, code: str) -> float:
    """Benchmark a single mirror and return speed in bytes/sec."""
    try:
        target_size = 100 * 1024 * 1024
        url = f"https://{code}.put.io/network.js/server.php?module=download&size={target_size}&network-{int(time.time()*1000)}"
        log.debug(f"Benchmarking {name} ({code})...")

        start_time = time.time()
        downloaded = 0

        # We need a short timeout for connection, but reasonable for download
        with httpx.Client(timeout=10.0) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes(chunk_size=8192):
                    downloaded += len(chunk)
                    elapsed = time.time() - start_time
                    # Stop if we have enough data or taken too long (e.g. 5 seconds)
                    if downloaded >= target_size or elapsed > 5:
                        break

        duration = time.time() - start_time
        if duration == 0: duration = 0.001
        speed = downloaded / duration
        log.info(f"Mirror {name}: {speed/1024/1024:.2f} MB/s")
        return speed
    except Exception as e:
        log.warning(f"Failed to benchmark {name} ({code}): {e}")
        return 0.0


def get_mirror_rankings(config: Config) -> list[dict]:
    """
    Returns a sorted list of mirrors [{'name': name, 'code': code, 'speed': speed}].
    """
    results = []

    should_benchmark = True
    if not config.mirrors['benchmark_only'] and config.mirrors['benchmark_file'].exists():
        try:
            with open(config.mirrors['benchmark_file'], 'r') as f:
                saved_data = json.load(f)
                results = saved_data
                should_benchmark = False
                log.info(f"Loaded benchmark results from {config.mirrors['benchmark_file']}")
        except Exception as e:
            log.warning(f"Could not load benchmark file: {e}. Re-running benchmark.")

    if should_benchmark:
        log.info("Benchmarking mirrors (this may take a moment)...")
        for name, code in config.mirrors['map'].items():
            speed = benchmark_mirror(name, code)
            results.append({'name': name, 'code': code, 'speed': speed})

        try:
            with open(config.mirrors['benchmark_file'], 'w') as f:
                json.dump(results, f, indent=2)
            log.info(f"Saved benchmark results to {config.mirrors['benchmark_file']}")
        except Exception as e:
            log.error(f"Failed to save benchmark results: {e}")

    # Filter by speed
    min_speed = config.mirrors['min_speed_bytes']

    filtered_results = []
    for r in results:
        # Check if speed meets requirement
        s = r.get('speed', 0)
        if s >= min_speed:
            filtered_results.append(r)
        else:
            log.info(f"Skipping mirror {r['name']} (Speed: {s/1024/1024:.2f} MB/s < Min: {min_speed/1024/1024:.2f} MB/s)")

    # Sort descending
    filtered_results.sort(key=lambda x: x['speed'], reverse=True)
    return filtered_results
