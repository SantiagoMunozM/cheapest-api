#!/usr/bin/env python3
"""Walk results/{get,post}_campaign/<scenario>/run<N>/ and build the report table.

Reuses the exact same percentile/error definitions as load_test.py so the
summary table matches what each run printed to console.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

SCENARIOS = {
    "alta_carga": {"label": "Alta carga", "users": 1500, "ramp_up": 75, "duration": 60},
    "muy_alta_carga": {"label": "Muy alta carga", "users": 3000, "ramp_up": 100, "duration": 60},
    "estres": {"label": "Estrés", "users": 7500, "ramp_up": 150, "duration": 60},
    "estres_fuerte": {"label": "Estrés fuerte (pico)", "users": 18000, "ramp_up": 200, "duration": 60},
}


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


def read_rows(csv_path: Path) -> list[dict]:
    if not csv_path.exists():
        return []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def summarize(rows: list[dict], elapsed_s: float) -> dict:
    total = len(rows)
    latencies = [float(r["latency_ms"]) for r in rows]
    errors = sum(1 for r in rows if r["status_code"] == "" or int(r["status_code"] or 0) >= 400)
    return {
        "total": total,
        "throughput": (total / elapsed_s) if elapsed_s > 0 else 0.0,
        "avg": (sum(latencies) / total) if total else 0.0,
        "p95": percentile(latencies, 95),
        "p99": percentile(latencies, 99),
        "error_pct": (errors / total * 100) if total else 0.0,
    }


def run_number(dirname: str) -> int:
    m = re.match(r"run(\d+)$", dirname)
    return int(m.group(1)) if m else 0


def main() -> None:
    base = Path(__file__).resolve().parent / "results"
    out_rows = []

    for campaign, endpoint in (("get_campaign", "get"), ("post_campaign", "post")):
        campaign_dir = base / campaign
        if not campaign_dir.exists():
            continue
        for scenario_key, meta in SCENARIOS.items():
            scenario_dir = campaign_dir / scenario_key
            if not scenario_dir.exists():
                continue
            run_dirs = sorted(
                (d for d in scenario_dir.iterdir() if d.is_dir() and d.name.startswith("run")),
                key=lambda d: run_number(d.name),
            )
            for run_dir in run_dirs:
                csv_path = run_dir / f"results_{endpoint}.csv"
                rows = read_rows(csv_path)
                if not rows:
                    continue
                # actual elapsed wall time for this run, read back from console.log if present,
                # else fall back to the nominal ramp_up+duration (slightly less precise).
                elapsed = meta["ramp_up"] + meta["duration"]
                console_log = run_dir / "console.log"
                if console_log.exists():
                    text = console_log.read_text(encoding="utf-8", errors="ignore")
                    m = re.search(r"wall time:\s*([\d.]+)s", text)
                    if m:
                        elapsed = float(m.group(1))
                stats = summarize(rows, elapsed)
                out_rows.append(
                    {
                        "Escenario": meta["label"],
                        "Endpoint": endpoint.upper(),
                        "Corrida": run_number(run_dir.name),
                        "Users": meta["users"],
                        "RampUp_s": meta["ramp_up"],
                        "Duracion_s": meta["duration"],
                        "Total": stats["total"],
                        "Throughput_rps": round(stats["throughput"], 2),
                        "Avg_ms": round(stats["avg"], 1),
                        "p95_ms": round(stats["p95"], 1),
                        "p99_ms": round(stats["p99"], 1),
                        "Error_pct": round(stats["error_pct"], 2),
                    }
                )

    out_path = base / "summary_table.csv"
    if out_rows:
        with open(out_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
            writer.writeheader()
            writer.writerows(out_rows)
        print(f"Wrote {len(out_rows)} rows -> {out_path}")
    else:
        print("No run results found yet; nothing to aggregate.")


if __name__ == "__main__":
    main()
