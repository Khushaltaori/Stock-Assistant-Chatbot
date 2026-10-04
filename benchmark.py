"""
benchmark.py — Repeatable latency benchmark for /chat endpoint.
Usage:
    python benchmark.py [--url URL] [--n N] [--delay DELAY] [--label LABEL]

Defaults:
    --url   http://127.0.0.1:8000/chat
    --n     5
    --delay 15   (seconds between requests, respects free-tier limits)
    --label baseline
"""
import argparse
import json
import statistics
import sys
import time
import requests

QUERY = {"message": "What is the current price of Reliance?"}

def run_benchmark(url: str, n: int, delay: float, label: str):
    latencies = []
    errors = []

    print(f"\n{'='*60}")
    print(f"BENCHMARK: {label}")
    print(f"  URL:   {url}")
    print(f"  Query: {QUERY['message']}")
    print(f"  N:     {n}  |  Delay: {delay}s between requests")
    print(f"{'='*60}\n")

    for i in range(n):
        if i > 0:
            print(f"  Waiting {delay}s...\n")
            time.sleep(delay)

        t0 = time.perf_counter()
        try:
            resp = requests.post(url, json=QUERY, timeout=60)
            elapsed = time.perf_counter() - t0
            if resp.status_code == 200:
                data = resp.json()
                answer_snippet = data.get("answer", "")[:80].replace("\n", " ")
                latencies.append(elapsed)
                print(f"  [{i+1}/{n}] {elapsed:.3f}s  ✓  \"{answer_snippet}...\"")
            else:
                elapsed_err = time.perf_counter() - t0
                errors.append((i+1, resp.status_code))
                print(f"  [{i+1}/{n}] {elapsed_err:.3f}s  ✗  HTTP {resp.status_code}")
        except Exception as e:
            elapsed_err = time.perf_counter() - t0
            errors.append((i+1, str(e)))
            print(f"  [{i+1}/{n}] {elapsed_err:.3f}s  ✗  Exception: {e}")

    print(f"\n{'='*60}")
    print(f"RESULTS: {label}")
    print(f"{'='*60}")
    print(f"  Successful:  {len(latencies)}/{n}")
    print(f"  Failed:      {len(errors)}")

    if latencies:
        avg  = statistics.mean(latencies)
        med  = statistics.median(latencies)
        mn   = min(latencies)
        mx   = max(latencies)
        print(f"  Average:     {avg:.3f}s")
        print(f"  Median:      {med:.3f}s")
        print(f"  Min:         {mn:.3f}s")
        print(f"  Max:         {mx:.3f}s")
        if len(latencies) >= 5:
            sorted_l = sorted(latencies)
            p95_idx = int(0.95 * len(sorted_l))
            p95 = sorted_l[min(p95_idx, len(sorted_l)-1)]
            print(f"  P95:         {p95:.3f}s  (note: small sample, treat as indicative)")
        print(f"\n  Raw (s):     {[round(x,3) for x in latencies]}")
    else:
        print("  No successful requests — cannot compute stats.")

    if errors:
        print(f"\n  Errors: {errors}")

    print(f"{'='*60}\n")

    return {
        "label": label,
        "n": n,
        "successful": len(latencies),
        "latencies": latencies,
        "avg": statistics.mean(latencies) if latencies else None,
        "median": statistics.median(latencies) if latencies else None,
        "min": min(latencies) if latencies else None,
        "max": max(latencies) if latencies else None,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url",   default="http://127.0.0.1:8000/chat")
    parser.add_argument("--n",     type=int,   default=5)
    parser.add_argument("--delay", type=float, default=15.0)
    parser.add_argument("--label", default="baseline")
    args = parser.parse_args()

    result = run_benchmark(args.url, args.n, args.delay, args.label)
    sys.exit(0 if result["successful"] > 0 else 1)
