"""
load_test.py — Basit GUI endpoint yük testi.

Kullanım:
    python scripts/load_test.py
    python scripts/load_test.py --host http://localhost:8050 --concurrency 5 --rounds 3
"""

import argparse
import asyncio
import time

import httpx

ENDPOINTS = ["/", "/overview", "/datacenters"]


async def fetch(client: httpx.AsyncClient, url: str) -> tuple[str, float, int]:
    start = time.perf_counter()
    try:
        resp = await client.get(url, timeout=30.0)
        elapsed = time.perf_counter() - start
        return url, elapsed, resp.status_code
    except Exception:
        elapsed = time.perf_counter() - start
        return url, elapsed, -1


async def run_load_test(host: str, concurrency: int, rounds: int) -> None:
    print(f"Hedef: {host}")
    print(f"Eşzamanlılık: {concurrency} | Tur: {rounds} | Endpoint: {ENDPOINTS}\n")

    async with httpx.AsyncClient(base_url=host) as client:
        total_requests = 0
        errors = 0
        all_times: list[float] = []

        for round_num in range(1, rounds + 1):
            tasks = [fetch(client, ep) for ep in ENDPOINTS for _ in range(concurrency)]
            start = time.perf_counter()
            results = await asyncio.gather(*tasks)
            elapsed = time.perf_counter() - start

            round_times = [r[1] for r in results]
            round_errors = sum(1 for r in results if r[2] < 0 or r[2] >= 400)
            all_times.extend(round_times)
            errors += round_errors
            total_requests += len(tasks)

            print(
                f"Tur {round_num}/{rounds}: {len(tasks)} istek | "
                f"{elapsed:.2f}s | {len(tasks) / elapsed:.1f} istek/s | "
                f"hata: {round_errors}"
            )

        print(f"\n{'=' * 40}")
        print(f"ÖZET")
        print(f"{'=' * 40}")
        print(f"Toplam istek : {total_requests}")
        print(f"Hata         : {errors} ({errors / total_requests * 100:.1f}%)")
        print(f"Ort. süre    : {sum(all_times) / len(all_times) * 1000:.0f} ms")
        print(f"Max süre     : {max(all_times) * 1000:.0f} ms")
        print(f"Min süre     : {min(all_times) * 1000:.0f} ms")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Datalake GUI yük testi")
    parser.add_argument("--host", default="http://localhost:8050", help="Hedef host")
    parser.add_argument("--concurrency", type=int, default=5, help="Eşzamanlı istek sayısı")
    parser.add_argument("--rounds", type=int, default=3, help="Tur sayısı")
    args = parser.parse_args()
    asyncio.run(run_load_test(args.host, args.concurrency, args.rounds))
