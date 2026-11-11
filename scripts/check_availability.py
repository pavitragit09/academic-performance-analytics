"""Availability polling and evidence collection script (APAS-NF-002).

Probes the APAS health endpoint, computes success percentage against the 99.5%
availability target, and logs evidence.
"""

import argparse
from datetime import datetime, timezone
import json
import sys
import time
import urllib.error
import urllib.request


def probe_once(url: str, timeout: float = 5.0) -> tuple[bool, int, float]:
    """Probe the health endpoint once. Returns (is_success, status_code, elapsed_ms)."""
    start = time.perf_counter()
    req = urllib.request.Request(url, headers={"User-Agent": "APAS-Availability-Checker/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.getcode()
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            return (status == 200, status, round(elapsed_ms, 2))
    except urllib.error.HTTPError as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return (False, exc.code, round(elapsed_ms, 2))
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return (False, 0, round(elapsed_ms, 2))


def run_checks(
    url: str,
    count: int = 1,
    interval: float = 1.0,
    output_path: str | None = None,
) -> dict:
    """Run count probes against url and return a summary."""
    successful = 0
    probes = []

    for i in range(count):
        is_ok, status, ms = probe_once(url)
        if is_ok:
            successful += 1
        probes.append({
            "probe": i + 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "success": is_ok,
            "latencyMs": ms,
        })
        if i + 1 < count:
            time.sleep(interval)

    total = len(probes)
    pct = round((successful / total) * 100.0, 2) if total > 0 else 0.0
    summary = {
        "url": url,
        "totalProbes": total,
        "successfulProbes": successful,
        "failedProbes": total - successful,
        "availabilityPercentage": pct,
        "targetPercentage": 99.5,
        "meetsTarget": pct >= 99.5,
        "probes": probes,
    }

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="APAS availability check script (NF-002)")
    parser.add_argument(
        "--url",
        default="http://localhost:8000/api/v1/health",
        help="Health check endpoint URL",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="Number of probes to perform",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Interval between probes in seconds",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to save JSON evidence log",
    )
    args = parser.parse_args()

    print(f"Checking availability of {args.url} ({args.count} probes)...")
    summary = run_checks(args.url, args.count, args.interval, args.output)

    print(f"Results: {summary['successfulProbes']}/{summary['totalProbes']} probes succeeded")
    print(f"Availability: {summary['availabilityPercentage']}% (Target: {summary['targetPercentage']}%)")
    print(f"Meets NF-002 SLA: {summary['meetsTarget']}")

    return 0 if summary["meetsTarget"] else 1


if __name__ == "__main__":
    sys.exit(main())
