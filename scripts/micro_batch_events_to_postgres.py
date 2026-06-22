#!/usr/bin/env python3
"""
Flux micro-batch MongoDB -> PostgreSQL:
- Lecture des événements par fenêtres temporelles
- Agrégation par type d'événement
- Persistance des métriques en base + historique KPI JSONL
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import psycopg2
from pymongo import MongoClient


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_STATE_FILE = ROOT_DIR / "logs" / "micro_batch_state.json"
TRANSFER_KPI_HISTORY_FILE = ROOT_DIR / "logs" / "transfer_kpi_history.jsonl"


def parse_iso8601(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def to_iso8601(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def postgres_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "kivendtout"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
    )


def mongo_client():
    return MongoClient(
        host=os.getenv("MONGODB_HOST", "localhost"),
        port=int(os.getenv("MONGODB_PORT", "27017")),
        username=os.getenv("MONGODB_USER", "admin"),
        password=os.getenv("MONGODB_PASSWORD", "admin"),
        authSource=os.getenv("MONGODB_AUTH_SOURCE", "admin"),
        serverSelectionTimeoutMS=5000,
    )


def ensure_micro_batch_table() -> None:
    with postgres_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS micro_batch_event_metrics (
                    batch_metric_id BIGSERIAL PRIMARY KEY,
                    batch_started_at TIMESTAMP NOT NULL,
                    batch_ended_at TIMESTAMP NOT NULL,
                    event_type VARCHAR(80) NOT NULL,
                    events_count INT NOT NULL,
                    latency_ms DOUBLE PRECISION NOT NULL,
                    speed_events_per_sec DOUBLE PRECISION NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (batch_started_at, batch_ended_at, event_type)
                );

                CREATE INDEX IF NOT EXISTS idx_micro_batch_metrics_end
                    ON micro_batch_event_metrics(batch_ended_at DESC);
                CREATE INDEX IF NOT EXISTS idx_micro_batch_metrics_event_type
                    ON micro_batch_event_metrics(event_type);
                """
            )
        conn.commit()


def load_state(state_file: Path, bootstrap_minutes: int) -> datetime:
    if state_file.exists():
        try:
            payload = json.loads(state_file.read_text(encoding="utf-8"))
            watermark = parse_iso8601(str(payload["watermark_utc"]))
            return watermark
        except Exception:
            pass
    return datetime.now(timezone.utc) - timedelta(minutes=max(1, bootstrap_minutes))


def save_state(state_file: Path, watermark: datetime) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "watermark_utc": to_iso8601(watermark),
        "updated_at_utc": to_iso8601(datetime.now(timezone.utc)),
    }
    state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _coerce_event_ts(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        ts = value
    else:
        ts = parse_iso8601(str(value))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def fetch_event_bounds() -> Tuple[Optional[datetime], Optional[datetime]]:
    client = mongo_client()
    try:
        db = client[os.getenv("MONGODB_DB", "kivendtout")]
        coll = db[os.getenv("MONGODB_COLLECTION", "events")]
        first = next(iter(coll.find({}, {"ts": 1, "_id": 0}).sort("ts", 1).limit(1)), None)
        last = next(iter(coll.find({}, {"ts": 1, "_id": 0}).sort("ts", -1).limit(1)), None)
        return _coerce_event_ts((first or {}).get("ts")), _coerce_event_ts((last or {}).get("ts"))
    finally:
        client.close()


def resolve_initial_watermark(
    state_file: Path,
    bootstrap_minutes: int,
    watermark_utc: str | None,
    window_seconds: int,
    anchor_mode: str,
) -> Tuple[datetime, dict]:
    source_min_ts, source_max_ts = fetch_event_bounds()
    metadata = {
        "anchor_mode": anchor_mode,
        "source_min_ts_utc": to_iso8601(source_min_ts) if source_min_ts else None,
        "source_max_ts_utc": to_iso8601(source_max_ts) if source_max_ts else None,
        "watermark_origin": "state",
        "watermark_adjusted": False,
    }

    if watermark_utc:
        watermark = parse_iso8601(watermark_utc)
        metadata["watermark_origin"] = "override"
    else:
        watermark = load_state(state_file, bootstrap_minutes=bootstrap_minutes)

    if not source_max_ts:
        return watermark, metadata

    latest_window_start = source_max_ts - timedelta(seconds=max(1, window_seconds))

    if anchor_mode == "latest-data":
        watermark = latest_window_start
        metadata["watermark_origin"] = "latest-data"
        metadata["watermark_adjusted"] = True
        return watermark, metadata

    if anchor_mode == "auto":
        if watermark >= source_max_ts or watermark < (source_min_ts or watermark):
            watermark = latest_window_start
            metadata["watermark_origin"] = "auto-latest-data"
            metadata["watermark_adjusted"] = True
        return watermark, metadata

    return watermark, metadata


def fetch_batch_events(start_dt: datetime, end_dt: datetime) -> List[Dict]:
    start_iso = to_iso8601(start_dt)
    end_iso = to_iso8601(end_dt)
    start_naive = start_dt.astimezone(timezone.utc).replace(tzinfo=None)
    end_naive = end_dt.astimezone(timezone.utc).replace(tzinfo=None)

    client = mongo_client()
    try:
        db = client[os.getenv("MONGODB_DB", "kivendtout")]
        coll = db[os.getenv("MONGODB_COLLECTION", "events")]
        query = {
            "$or": [
                {"ts": {"$gt": start_naive, "$lte": end_naive}},
                {"ts": {"$gt": start_iso, "$lte": end_iso}},
            ]
        }
        projection = {"_id": 0, "event_type": 1, "ts": 1}
        return list(coll.find(query, projection))
    finally:
        client.close()


def persist_batch_metrics(
    start_dt: datetime,
    end_dt: datetime,
    counters: Counter,
    latency_ms: float,
    speed_events_per_sec: float,
) -> None:
    if not counters:
        counters = Counter({"NO_EVENTS": 0})

    with postgres_conn() as conn:
        with conn.cursor() as cursor:
            for event_type, count in counters.items():
                cursor.execute(
                    """
                    INSERT INTO micro_batch_event_metrics (
                        batch_started_at,
                        batch_ended_at,
                        event_type,
                        events_count,
                        latency_ms,
                        speed_events_per_sec,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (batch_started_at, batch_ended_at, event_type)
                    DO UPDATE SET
                        events_count = EXCLUDED.events_count,
                        latency_ms = EXCLUDED.latency_ms,
                        speed_events_per_sec = EXCLUDED.speed_events_per_sec,
                        created_at = EXCLUDED.created_at
                    """,
                    (
                        start_dt.replace(tzinfo=None),
                        end_dt.replace(tzinfo=None),
                        event_type,
                        int(count),
                        float(latency_ms),
                        float(speed_events_per_sec),
                        datetime.now(timezone.utc).replace(tzinfo=None),
                    ),
                )
        conn.commit()


def append_transfer_kpi(
    start_dt: datetime,
    end_dt: datetime,
    events_count: int,
    latency_ms: float,
    speed_events_per_sec: float,
    event_types_count: int,
    anchor_mode: str,
    source_max_ts: Optional[datetime],
) -> None:
    payload = {
        "metric": "micro_batch_events",
        "timestamp_utc": to_iso8601(datetime.now(timezone.utc)),
        "batch_started_at": to_iso8601(start_dt),
        "batch_ended_at": to_iso8601(end_dt),
        "latency_ms": round(float(latency_ms), 2),
        "capacity_events": int(events_count),
        "speed_events_per_second": round(float(speed_events_per_sec), 2),
        "event_types_count": int(event_types_count),
        "anchor_mode": anchor_mode,
        "source_max_ts_utc": to_iso8601(source_max_ts) if source_max_ts else None,
    }
    TRANSFER_KPI_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with TRANSFER_KPI_HISTORY_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")


def run_micro_batch(
    window_seconds: int,
    poll_interval: float,
    duration_seconds: int,
    run_once: bool,
    bootstrap_minutes: int,
    state_file: Path,
    watermark_utc: str | None,
    anchor_mode: str,
) -> int:
    ensure_micro_batch_table()
    watermark, source_meta = resolve_initial_watermark(
        state_file=state_file,
        bootstrap_minutes=bootstrap_minutes,
        watermark_utc=watermark_utc,
        window_seconds=window_seconds,
        anchor_mode=anchor_mode,
    )
    started_at = time.time()
    batches_done = 0

    print("=== MICRO-BATCH EVENTS -> POSTGRES ===")
    print(f"window_seconds   : {window_seconds}")
    print(f"poll_interval    : {poll_interval}")
    print(f"duration_seconds : {duration_seconds if duration_seconds > 0 else 'infinite'}")
    print(f"state_file       : {state_file}")
    print(f"anchor_mode      : {anchor_mode}")
    if source_meta.get("source_max_ts_utc"):
        print(f"source_max_ts    : {source_meta['source_max_ts_utc']}")
    print(f"initial_watermark: {to_iso8601(watermark)}")

    while True:
        now_utc = datetime.now(timezone.utc)
        if duration_seconds > 0 and (time.time() - started_at) >= duration_seconds:
            break

        batch_start = watermark
        batch_end = batch_start + timedelta(seconds=window_seconds)
        if batch_end > now_utc:
            time.sleep(poll_interval)
            continue

        process_started_at = time.perf_counter()
        events = fetch_batch_events(batch_start, batch_end)
        counters = Counter((item.get("event_type") or "unknown").strip() or "unknown" for item in events)
        total_events = sum(counters.values())
        processing_latency_ms = max(1.0, (time.perf_counter() - process_started_at) * 1000.0)
        speed_events_per_sec = float(total_events) / (processing_latency_ms / 1000.0) if processing_latency_ms > 0 else 0.0
        event_types_count = len([event_type for event_type, count in counters.items() if event_type != "NO_EVENTS" and count > 0])
        _, source_max_ts = fetch_event_bounds() if run_once else (None, source_meta.get("source_max_ts_utc"))
        source_max_dt = source_max_ts if isinstance(source_max_ts, datetime) else _coerce_event_ts(source_max_ts)

        persist_batch_metrics(
            start_dt=batch_start,
            end_dt=batch_end,
            counters=counters,
            latency_ms=processing_latency_ms,
            speed_events_per_sec=speed_events_per_sec,
        )
        append_transfer_kpi(
            start_dt=batch_start,
            end_dt=batch_end,
            events_count=total_events,
            latency_ms=processing_latency_ms,
            speed_events_per_sec=speed_events_per_sec,
            event_types_count=event_types_count,
            anchor_mode=anchor_mode,
            source_max_ts=source_max_dt,
        )

        watermark = batch_end
        save_state(state_file, watermark)
        batches_done += 1

        print(
            f"[batch {batches_done:04d}] "
            f"window={to_iso8601(batch_start)}->{to_iso8601(batch_end)} "
            f"events={total_events} types={len(counters)} "
            f"processing_latency_ms={processing_latency_ms:.2f} speed_events_per_sec={speed_events_per_sec:.2f}"
        )

        if run_once:
            break

    print(f"Micro-batch terminé. batches_done={batches_done}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Flux micro-batch MongoDB -> PostgreSQL")
    parser.add_argument("--window-seconds", type=int, default=30, help="Taille de fenêtre micro-batch")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Sleep entre cycles")
    parser.add_argument("--duration-seconds", type=int, default=0, help="0 = infini")
    parser.add_argument("--run-once", action="store_true", help="Exécute un seul batch")
    parser.add_argument("--bootstrap-minutes", type=int, default=10, help="Watermark initial si état absent")
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE), help="Fichier watermark JSON")
    parser.add_argument("--watermark-utc", default=None, help="Override watermark initial (ISO8601)")
    parser.add_argument(
        "--anchor-mode",
        default=os.getenv("MICRO_BATCH_ANCHOR_MODE", "auto"),
        choices=["auto", "state", "latest-data"],
        help="Mode d'ancrage du watermark: auto, state, latest-data",
    )
    args = parser.parse_args()

    return run_micro_batch(
        window_seconds=max(1, int(args.window_seconds)),
        poll_interval=max(0.1, float(args.poll_interval)),
        duration_seconds=max(0, int(args.duration_seconds)),
        run_once=bool(args.run_once),
        bootstrap_minutes=max(1, int(args.bootstrap_minutes)),
        state_file=Path(args.state_file).resolve(),
        watermark_utc=args.watermark_utc,
        anchor_mode=str(args.anchor_mode),
    )


if __name__ == "__main__":
    raise SystemExit(main())
