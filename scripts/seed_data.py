#!/usr/bin/env python3
"""
Generate sample data for development / UI preview.

Usage:
    python scripts/seed_data.py             # generates 7 days of data
    python scripts/seed_data.py --days 30   # generates 30 days
    python scripts/seed_data.py --clear     # wipes existing data first
"""

from __future__ import annotations
import argparse
import json
import math
import random
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from claude_hourglass import config, database
from claude_hourglass.models import UsageSnapshot

MODELS = [
    "Claude Sonnet 4.6",
    "Claude Opus 4.7",
    "Claude Haiku 4.5",
]

SESSIONS_PER_DAY_RANGE = (1, 4)
SNAPSHOTS_PER_SESSION_RANGE = (6, 24)


def _random_session_id() -> str:
    import uuid
    return str(uuid.uuid4())


def _simulate_session(
    start: datetime,
    base_5h_pct: float,
    base_7d_pct: float,
    cost_start: float,
    session_id: str,
    model: str,
) -> list[UsageSnapshot]:
    """Simulate a single session's worth of snapshots."""
    count = random.randint(*SNAPSHOTS_PER_SESSION_RANGE)
    snaps = []

    five_hour_pct = base_5h_pct
    seven_day_pct = base_7d_pct
    cost = cost_start
    context = random.randint(5_000, 30_000)

    for i in range(count):
        ts = start + timedelta(minutes=i * random.uniform(2, 8))
        # Usage climbs during session with random jitter
        five_hour_pct = min(100.0, five_hour_pct + random.uniform(0.5, 4.0))
        seven_day_pct = min(100.0, seven_day_pct + random.uniform(0.1, 0.8))
        cost += random.uniform(0.001, 0.05)
        context += random.randint(100, 2000)

        # Compute reset times (5h from capture_at rounded to hour)
        five_h_reset = ts.replace(minute=0, second=0, microsecond=0) + timedelta(hours=5)
        seven_d_reset = (ts + timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)

        data = {
            "captured_at": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "session_id": session_id,
            "model": {"display_name": model},
            "rate_limits": {
                "five_hour": {
                    "used_percentage": round(five_hour_pct, 2),
                    "resets_at": five_h_reset.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
                "seven_day": {
                    "used_percentage": round(seven_day_pct, 2),
                    "resets_at": seven_d_reset.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            },
            "cost": {"total_cost_usd": round(cost, 6)},
            "context_window": {"current_usage": context},
            "version": "1.0.0",
        }
        snaps.append(UsageSnapshot.from_status_json(data))

    return snaps


def generate(days: int, db_path: Path, json_path: Path) -> int:
    database.init(db_path)

    now = datetime.now(timezone.utc)
    total = 0

    for day_offset in range(days - 1, -1, -1):
        day_start = (now - timedelta(days=day_offset)).replace(
            hour=8, minute=0, second=0, microsecond=0
        )

        # Simulate varying usage patterns across the week
        # (weekdays busier than weekends)
        weekday = day_start.weekday()
        activity = 0.9 if weekday < 5 else 0.3

        n_sessions = random.randint(*SESSIONS_PER_DAY_RANGE)
        if random.random() > activity:
            n_sessions = max(0, n_sessions - 2)

        five_h_baseline = random.uniform(0, 30)
        seven_d_baseline = random.uniform(5, 40)
        cost_accum = random.uniform(0, 0.5)

        session_start = day_start
        for _ in range(n_sessions):
            session_id = _random_session_id()
            model = random.choice(MODELS)

            snaps = _simulate_session(
                session_start,
                five_h_baseline,
                seven_d_baseline,
                cost_accum,
                session_id,
                model,
            )

            for snap in snaps:
                database.insert(db_path, snap)
                total += 1

            # Between sessions: usage may reset or carry over
            five_h_baseline = random.uniform(0, 20) if random.random() > 0.5 else 0.0
            cost_accum = (snaps[-1].total_cost_usd or cost_accum) + random.uniform(0, 0.1)
            session_start += timedelta(hours=random.uniform(1, 4))

    # Write latest snapshot to JSON
    latest = database.latest(db_path)
    if latest and latest.raw_json:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(latest.raw_json, encoding="utf-8")

    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate sample usage data")
    parser.add_argument("--days", type=int, default=7, help="Days of history to generate")
    parser.add_argument("--clear", action="store_true", help="Clear existing data first")
    args = parser.parse_args()

    config.load()
    db_path = config.db_path()
    json_path = config.latest_json_path()

    if args.clear and db_path.exists():
        con = sqlite3.connect(str(db_path))
        con.execute("DELETE FROM usage_snapshots")
        con.commit()
        con.close()
        print(f"Cleared existing data in {db_path}")

    print(f"Generating {args.days} days of sample data...")
    count = generate(args.days, db_path, json_path)
    print(f"Done: {count} snapshots saved to {db_path}")
    print(f"Latest snapshot also written to {json_path}")


if __name__ == "__main__":
    main()
