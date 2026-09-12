#!/usr/bin/env python3
"""Async load generator for the cheapest-api logistics endpoints.

Used for Lab 2 test-matrix runs above JMeter's 450-thread ceiling (Alta
carga / Muy alta carga / Estres / Estres fuerte-pico). Drives:

  GET  /logistics/tenderos/productos-disponibles?tiendaId=&zona=
  POST /logistics/pedidos

Requires exactly one third-party dependency: httpx (async HTTP client).
Everything else is standard library. matplotlib is optional and only
used if installed and --plots is passed.

Install:
    pip install httpx
    pip install matplotlib   # optional, only for --plots

Generate a realistic >20-item POST body once (fetches real productoIds
from the running API, falls back to the fixed seed.sql products if the
API/catalog is unreachable or empty):

    python load_test.py --make-sample-body sample_body.json

Run examples:
    # GET campaign (ASR1): p99 < 1000ms @ 500 req/min ~= 8.3 req/s
    python load_test.py --endpoint get --users 1500 --ramp-up 75 --duration 60

    # POST campaign (ASR2): error% <= 2% @ 5000 req/min ~= 83 req/s
    python load_test.py --users 100 --ramp-up 50 --duration 60 --endpoint POST --body sample_body.json

Outputs (written to --output-dir, default: this script's directory):
    results_get.csv, results_post.csv  (timestamp_iso,status_code,latency_ms,error)
    a console summary with per-type totals, throughput, avg/p95/p99, error%
    latency_get.png / latency_post.png / throughput.png if --plots and matplotlib is installed

Notes:
    - --duration is the hold time AFTER ramp-up completes, not counting it
      (matches the lab statement: "el script corre --duration segundos
      sosteniendo la concurrencia objetivo"). Users start staggered over
      --ramp-up seconds and all keep looping back-to-back requests (no
      think time); the test's total wall time is ramp-up + duration.
    - At very high --users (thousands), this single Python process becomes
      itself a bottleneck (event loop, sockets, GIL-bound JSON/TLS work)
      before the server's connection pool does. Raise your file descriptor
      limit first (`ulimit -n 20000`) and, if throughput plateaus while
      client CPU is pegged at ~100%, split the run across multiple
      processes/machines to tell client-side limits apart from server-side
      ones (relevant to the lab's connection-pool-vs-query-cost question).
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import csv
import json
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

try:
    import httpx
except ImportError:
    print(
        "Missing dependency 'httpx'. Install it with:\n\n    pip install httpx\n",
        file=sys.stderr,
    )
    sys.exit(1)

GET_PATH = "/logistics/tenderos/productos-disponibles"
POST_PATH = "/logistics/pedidos"
PRODUCTOS_PATH = "/logistics/productos"

# Fixed seed.sql defaults (see database-seeder.service.ts / seed.sql).
DEFAULT_BASE_URL = "http://localhost:3000"
DEFAULT_TIENDA_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
DEFAULT_ZONA = "Zona Norte"
DEFAULT_MONEDA_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
FALLBACK_PRODUCTO_IDS = [
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaab",
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaac",
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaad",
]

MIN_ITEMS_PER_PEDIDO = 21  # ">20 items" per lab requirement


@dataclass
class RequestResult:
    timestamp_iso: str
    method: str
    status_code: Optional[int]
    latency_ms: float
    error: str = ""


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Async load test for cheapest-api logistics endpoints.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default="get",
        help="Which endpoint to drive: get, post, or both (default: get).",
    )
    parser.add_argument("--users", type=int, default=50, help="Max concurrent virtual users.")
    parser.add_argument("--ramp-up", type=float, default=10.0, help="Seconds to stagger-start all users.")
    parser.add_argument(
        "--duration",
        type=float,
        default=60.0,
        help="Seconds to hold at full concurrency AFTER ramp-up completes (not counting ramp-up).",
    )
    parser.add_argument(
        "--body",
        type=str,
        default=None,
        help="Path to a JSON file with a CreatePedidoDto body to reuse for POST requests "
        "(identificador/fechaHoraCreacion/montoTotal are refreshed per request). "
        "If omitted, a realistic >20-item body is auto-generated per request.",
    )
    parser.add_argument(
        "--make-sample-body",
        type=str,
        default=None,
        metavar="PATH",
        help="Fetch real productoIds from the API and write a sample >20-item pedido body "
        "to PATH, then exit (no load test is run).",
    )
    parser.add_argument("--base-url", type=str, default=DEFAULT_BASE_URL)
    parser.add_argument("--tienda-id", type=str, default=DEFAULT_TIENDA_ID, help="Used for GET query and auto-generated POST bodies.")
    parser.add_argument("--zona", type=str, default=DEFAULT_ZONA)
    parser.add_argument("--moneda-id", type=str, default=DEFAULT_MONEDA_ID)
    parser.add_argument(
        "--items-per-pedido",
        type=int,
        default=25,
        help="Item count for auto-generated POST bodies (must be > 20).",
    )
    parser.add_argument(
        "--get-ratio",
        type=float,
        default=0.5,
        help="Fraction of requests that are GET when --endpoint=both (default: 0.5).",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="Per-request timeout in seconds.")
    parser.add_argument(
        "--max-connections",
        type=int,
        default=None,
        help="Client-side connection pool cap (default: same as --users).",
    )
    parser.add_argument("--output-dir", type=str, default=None, help="Where to write CSV/PNG output (default: this script's directory).")
    parser.add_argument("--plots", action="store_true", help="Also render latency/throughput charts (requires matplotlib).")
    parser.add_argument("--seed", type=int, default=None, help="Random seed, for reproducible auto-generated bodies.")

    args = parser.parse_args(argv)
    args.endpoint = args.endpoint.strip().lower()
    if args.endpoint not in ("get", "post", "both"):
        parser.error("--endpoint must be one of: get, post, both")
    if args.users < 1:
        parser.error("--users must be >= 1")
    if args.ramp_up < 0:
        parser.error("--ramp-up must be >= 0")
    if args.duration <= 0:
        parser.error("--duration must be > 0")
    if args.items_per_pedido <= 20:
        print(
            f"[warn] --items-per-pedido={args.items_per_pedido} is <= 20; "
            "the lab requires a 'pedido grande' with > 20 items.",
            file=sys.stderr,
        )
    if not args.max_connections:
        args.max_connections = args.users
    return args


# ---------------------------------------------------------------------
# POST body construction
# ---------------------------------------------------------------------


def load_template(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        template = json.load(fh)
    items = template.get("items", [])
    if len(items) <= 20:
        print(
            f"[warn] {path} has {len(items)} items; the lab requires > 20 items per pedido.",
            file=sys.stderr,
        )
    return template


def build_from_template(template: dict) -> dict:
    body = copy.deepcopy(template)
    body["identificador"] = f"LOAD-{uuid4()}"
    body["fechaHoraCreacion"] = datetime.now(timezone.utc).isoformat()
    items = body.get("items") or []
    if items:
        total = sum(
            float(item["cantidad"]) * float(item["precioUnitario"]) - float(item.get("descuento", 0) or 0)
            for item in items
        )
        body["montoTotal"] = round(max(total, 0.01), 2)
    return body


def make_item(product: dict, moneda_id: str) -> dict:
    cantidad = random.randint(1, 10)
    precio_base = product.get("precioBase")
    precio_unitario = float(precio_base) if precio_base is not None else round(random.uniform(5, 100), 2)
    descuento = round(precio_unitario * random.choice([0, 0, 0, 0.05, 0.1]), 2)
    return {
        "productoId": product["id"],
        "cantidad": cantidad,
        "precioUnitario": precio_unitario,
        "descuento": descuento,
        "monedaId": product.get("monedaId") or moneda_id,
        "lote": f"LOTE-{uuid4().hex[:8]}",
    }


def build_auto_pedido(args: argparse.Namespace, product_pool: list[dict]) -> dict:
    items = [make_item(random.choice(product_pool), args.moneda_id) for _ in range(args.items_per_pedido)]
    monto_total = round(
        sum(item["cantidad"] * item["precioUnitario"] - item["descuento"] for item in items), 2
    )
    return {
        "identificador": f"LOAD-{uuid4()}",
        "tiendaId": args.tienda_id,
        "fechaHoraCreacion": datetime.now(timezone.utc).isoformat(),
        "montoTotal": max(monto_total, 0.01),
        "monedaId": args.moneda_id,
        "items": items,
    }


async def fetch_product_pool(client: "httpx.AsyncClient", args: argparse.Namespace) -> list[dict]:
    try:
        resp = await client.get(PRODUCTOS_PATH, timeout=args.timeout)
        resp.raise_for_status()
        data = resp.json()
        pool = [
            {"id": p["id"], "monedaId": p.get("monedaId"), "precioBase": p.get("precioBase")}
            for p in data
            if isinstance(p, dict) and "id" in p
        ]
        if pool:
            print(f"[setup] Fetched {len(pool)} productos from {PRODUCTOS_PATH} for POST bodies.")
            return pool
    except Exception as exc:  # noqa: BLE001 - any fetch failure just falls back
        print(f"[setup] Could not fetch product catalog ({exc}); using fallback seed productos.")
    return [{"id": pid, "monedaId": None, "precioBase": None} for pid in FALLBACK_PRODUCTO_IDS]


def make_sample_body_file(args: argparse.Namespace) -> None:
    async def _run() -> dict:
        async with httpx.AsyncClient(base_url=args.base_url) as client:
            pool = await fetch_product_pool(client, args)
        return build_auto_pedido(args, pool)

    body = asyncio.run(_run())
    out_path = Path(args.make_sample_body)
    out_path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote sample pedido body ({len(body['items'])} items) to {out_path}")


# ---------------------------------------------------------------------
# Load generation
# ---------------------------------------------------------------------


async def send_request(
    client: "httpx.AsyncClient",
    args: argparse.Namespace,
    product_pool: Optional[list[dict]],
    template: Optional[dict],
) -> RequestResult:
    if args.endpoint == "both":
        use_get = random.random() < args.get_ratio
    else:
        use_get = args.endpoint == "get"

    method = "GET" if use_get else "POST"
    ts_iso = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    status_code: Optional[int] = None
    error = ""

    try:
        if use_get:
            resp = await client.get(
                GET_PATH,
                params={"tiendaId": args.tienda_id, "zona": args.zona},
            )
        else:
            body = build_from_template(template) if template is not None else build_auto_pedido(args, product_pool)
            resp = await client.post(POST_PATH, json=body)
        status_code = resp.status_code
        if status_code >= 400:
            error = f"HTTP {status_code}"
    except httpx.TimeoutException as exc:
        error = f"timeout: {exc.__class__.__name__}"
    except httpx.ConnectError as exc:
        error = f"connection_error: {exc}"
    except httpx.HTTPError as exc:
        error = f"http_error: {exc}"
    except Exception as exc:  # noqa: BLE001 - record and keep going
        error = f"error: {exc}"

    latency_ms = (time.monotonic() - start) * 1000
    return RequestResult(ts_iso, method, status_code, round(latency_ms, 2), error)


async def virtual_user(
    start_delay: float,
    end_time: float,
    client: "httpx.AsyncClient",
    args: argparse.Namespace,
    product_pool: Optional[list[dict]],
    template: Optional[dict],
    results: list[RequestResult],
) -> None:
    if start_delay > 0:
        await asyncio.sleep(start_delay)
    while time.monotonic() < end_time:
        result = await send_request(client, args, product_pool, template)
        results.append(result)


async def progress_reporter(end_time: float, results: list[RequestResult]) -> None:
    while True:
        remaining = end_time - time.monotonic()
        if remaining <= 0:
            return
        await asyncio.sleep(min(5.0, max(0.5, remaining)))
        total = len(results)
        errors = sum(1 for r in results if r.status_code is None or r.status_code >= 400)
        err_pct = (errors / total * 100) if total else 0.0
        print(
            f"[progress] t-{max(remaining, 0):5.1f}s remaining | "
            f"{total} requests so far | error rate {err_pct:.1f}%"
        )


async def run_load_test(args: argparse.Namespace) -> tuple[list[RequestResult], float]:
    results: list[RequestResult] = []
    timeout_cfg = httpx.Timeout(args.timeout)
    limits = httpx.Limits(
        max_connections=args.max_connections,
        max_keepalive_connections=args.max_connections,
    )

    async with httpx.AsyncClient(base_url=args.base_url, timeout=timeout_cfg, limits=limits) as client:
        product_pool: Optional[list[dict]] = None
        template: Optional[dict] = None

        if args.body:
            template = load_template(args.body)
        elif args.endpoint in ("post", "both"):
            product_pool = await fetch_product_pool(client, args)

        test_start = time.monotonic()
        end_time = test_start + args.ramp_up + args.duration

        print(
            f"Running: endpoint={args.endpoint} users={args.users} ramp_up={args.ramp_up}s "
            f"duration={args.duration}s (hold, after ramp-up) total~={args.ramp_up + args.duration}s "
            f"target={args.base_url}"
        )

        tasks = [
            asyncio.create_task(
                virtual_user(
                    (i / args.users) * args.ramp_up if args.users > 0 else 0.0,
                    end_time,
                    client,
                    args,
                    product_pool,
                    template,
                    results,
                )
            )
            for i in range(args.users)
        ]
        reporter = asyncio.create_task(progress_reporter(end_time, results))

        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            print("\n[!] Interrupted - cancelling remaining virtual users and reporting partial results...")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            reporter.cancel()
            await asyncio.gather(reporter, return_exceptions=True)

        actual_elapsed = time.monotonic() - test_start

    return results, actual_elapsed


# ---------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------


def percentile(data: list[float], pct: float) -> float:
    if not data:
        return 0.0
    data_sorted = sorted(data)
    k = (len(data_sorted) - 1) * (pct / 100)
    f = int(k)
    c = min(f + 1, len(data_sorted) - 1)
    if f == c:
        return data_sorted[f]
    return data_sorted[f] * (c - k) + data_sorted[c] * (k - f)


def is_error(result: RequestResult) -> bool:
    return result.status_code is None or result.status_code >= 400


def summarize(results: list[RequestResult], elapsed: float) -> dict:
    total = len(results)
    errors = sum(1 for r in results if is_error(r))
    latencies = [r.latency_ms for r in results]
    return {
        "total": total,
        "throughput": total / elapsed if elapsed > 0 else 0.0,
        "avg_latency_ms": (sum(latencies) / total) if total else 0.0,
        "p95_latency_ms": percentile(latencies, 95),
        "p99_latency_ms": percentile(latencies, 99),
        "error_pct": (errors / total * 100) if total else 0.0,
        "errors": errors,
    }


def write_csv(results: list[RequestResult], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["timestamp_iso", "status_code", "latency_ms", "error"])
        for r in results:
            writer.writerow([r.timestamp_iso, r.status_code if r.status_code is not None else "", r.latency_ms, r.error])


def print_summary(get_results: list[RequestResult], post_results: list[RequestResult], elapsed: float) -> None:
    print("\n" + "=" * 72)
    print(f"LOAD TEST SUMMARY (wall time: {elapsed:.1f}s)")
    print("=" * 72)
    for label, bucket in (("GET", get_results), ("POST", post_results)):
        if not bucket:
            continue
        stats = summarize(bucket, elapsed)
        print(f"\n{label}  ({stats['total']} requests)")
        print(f"  throughput   : {stats['throughput']:.2f} req/s")
        print(f"  avg latency  : {stats['avg_latency_ms']:.1f} ms")
        print(f"  p95 latency  : {stats['p95_latency_ms']:.1f} ms")
        print(f"  p99 latency  : {stats['p99_latency_ms']:.1f} ms")
        print(f"  error rate   : {stats['error_pct']:.2f}% ({stats['errors']}/{stats['total']})")
    print("\n" + "=" * 72)


def maybe_plot(get_results: list[RequestResult], post_results: list[RequestResult], out_dir: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[plots] matplotlib not installed; skipping charts (pip install matplotlib to enable).")
        return

    def _times(bucket: list[RequestResult]) -> list[datetime]:
        return [datetime.fromisoformat(r.timestamp_iso) for r in bucket]

    for label, bucket in (("get", get_results), ("post", post_results)):
        if not bucket:
            continue
        times = _times(bucket)
        t0 = times[0]
        xs = [(t - t0).total_seconds() for t in times]
        ys = [r.latency_ms for r in bucket]
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.scatter(xs, ys, s=4, alpha=0.4)
        ax.set_xlabel("seconds since test start")
        ax.set_ylabel("latency (ms)")
        ax.set_title(f"{label.upper()} latency over time")
        fig.tight_layout()
        fig.savefig(out_dir / f"latency_{label}.png", dpi=120)
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4))
    for label, bucket in (("GET", get_results), ("POST", post_results)):
        if not bucket:
            continue
        times = sorted(_times(bucket))
        t0 = times[0]
        buckets: dict[int, int] = {}
        for t in times:
            second = int((t - t0).total_seconds())
            buckets[second] = buckets.get(second, 0) + 1
        xs = sorted(buckets)
        ys = [buckets[x] for x in xs]
        ax.plot(xs, ys, label=label)
    ax.set_xlabel("seconds since test start")
    ax.set_ylabel("requests/sec")
    ax.set_title("Throughput over time")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "throughput.png", dpi=120)
    plt.close(fig)
    print(f"[plots] Charts written to {out_dir}")


# ---------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)

    if args.seed is not None:
        random.seed(args.seed)

    if args.make_sample_body:
        make_sample_body_file(args)
        return

    out_dir = Path(args.output_dir) if args.output_dir else Path(__file__).resolve().parent
    out_dir.mkdir(parents=True, exist_ok=True)

    results, elapsed = asyncio.run(run_load_test(args))

    get_results = [r for r in results if r.method == "GET"]
    post_results = [r for r in results if r.method == "POST"]

    write_csv(get_results, out_dir / "results_get.csv")
    write_csv(post_results, out_dir / "results_post.csv")
    print(f"\nWrote {len(get_results)} GET rows -> {out_dir / 'results_get.csv'}")
    print(f"Wrote {len(post_results)} POST rows -> {out_dir / 'results_post.csv'}")

    print_summary(get_results, post_results, elapsed)

    if args.plots:
        maybe_plot(get_results, post_results, out_dir)


if __name__ == "__main__":
    main()
