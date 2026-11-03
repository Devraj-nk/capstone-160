from __future__ import annotations

import argparse
import asyncio
import csv
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

def _normalize_text(s: str) -> str:
    return " ".join((s or "").split())


def _row_attributes(
    row: dict[str, str],
    *,
    text_col: str,
    tweet_id_col: str,
) -> dict[str, Any]:
    """Every non-empty column except the text becomes an attribute (the
    pipeline reads tweet_id, and later stages use account/location fields);
    the id column is always exposed as "tweet_id"."""
    attrs: dict[str, Any] = {
        key: value for key, value in row.items() if key and key != text_col and value not in (None, "")
    }
    if tweet_id_col in attrs:
        attrs["tweet_id"] = attrs.pop(tweet_id_col)
    return attrs


def _row_created_at(row: dict[str, str], timestamp_col: str | None) -> float:
    """The row's own timestamp (ISO-8601 or unix seconds) when asked for and
    parseable, else now — so replayed data can keep its original timing."""
    raw = (row.get(timestamp_col) or "").strip() if timestamp_col else ""
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return time.time()


async def _stream_csv(
    *,
    csv_path: Path,
    ingestion_url: str,
    text_col: str,
    tweet_id_col: str,
    timestamp_col: str | None,
    interval: float,
    min_interval: float | None,
    max_interval: float | None,
    loop: bool,
    limit: int,
) -> None:
    sent = 0

    use_random_interval = (min_interval is not None) or (max_interval is not None)
    if use_random_interval:
        min_wait = interval if min_interval is None else min_interval
        max_wait = interval if max_interval is None else max_interval

        if min_wait <= 0 or max_wait <= 0:
            raise SystemExit("--min-interval/--max-interval must be > 0")
        if max_wait < min_wait:
            raise SystemExit("--max-interval must be >= --min-interval")
    else:
        if interval <= 0:
            raise SystemExit("--interval must be > 0")

    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    raise SystemExit("CSV appears to have no header")

                if text_col not in reader.fieldnames:
                    raise SystemExit(
                        f"Missing text column '{text_col}'. Found columns: {reader.fieldnames}"
                    )

                for row in reader:
                    if limit and sent >= limit:
                        return

                    text = _normalize_text(row.get(text_col, ""))
                    if not text:
                        continue

                    sent += 1
                    payload = {
                        "text": text,
                        "created_at": _row_created_at(row, timestamp_col),
                        "attributes": _row_attributes(row, text_col=text_col, tweet_id_col=tweet_id_col),
                    }

                    try:
                        r = await client.post(ingestion_url, json=payload)
                        r.raise_for_status()
                        body = r.json()
                        label = payload["attributes"].get("label")
                        tweet_id = payload["attributes"].get("tweet_id")
                        print(
                            f"#{sent} sent tweet_id={tweet_id} label={label} -> ingested_id={body.get('ingested_id')} dropped_oldest={body.get('dropped_oldest')}"
                        )
                    except httpx.HTTPError as e:
                        print(f"#{sent} failed to send: {e}")

                    wait_s = (
                        random.uniform(min_wait, max_wait)
                        if use_random_interval
                        else interval
                    )
                    await asyncio.sleep(wait_s)

            if not loop:
                return


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stream a CSV dataset as JSON events into the ingestion pipeline"
    )
    parser.add_argument(
        "--csv-path",
        default="ingestion.csv",
        help="Path to CSV file (with header)",
    )
    parser.add_argument("--ingestion-url", default="http://127.0.0.1:8000/ingestion/ingest")

    parser.add_argument("--text-column", default="text")
    parser.add_argument("--tweet-id-column", default="post_id")
    parser.add_argument(
        "--timestamp-column",
        default=None,
        help="Use this column as created_at (ISO-8601 or unix seconds); default: send time",
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Seconds to wait between sending rows (deterministic)",
    )
    parser.add_argument(
        "--min-interval",
        type=float,
        default=None,
        help="Minimum seconds to wait between sending rows (randomized)",
    )
    parser.add_argument(
        "--max-interval",
        type=float,
        default=None,
        help="Maximum seconds to wait between sending rows (randomized)",
    )
    parser.add_argument("--loop", action="store_true", help="Loop over the CSV indefinitely")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Send at most N rows (0 = no limit)",
    )

    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        raise SystemExit(f"CSV file not found: {csv_path}")

    if args.min_interval is None and args.max_interval is None and args.interval <= 0:
        raise SystemExit("--interval must be > 0")

    if args.limit < 0:
        raise SystemExit("--limit must be >= 0")

    await _stream_csv(
        csv_path=csv_path,
        ingestion_url=args.ingestion_url,
        text_col=args.text_column,
        tweet_id_col=args.tweet_id_column,
        timestamp_col=args.timestamp_column,
        interval=args.interval,
        min_interval=args.min_interval,
        max_interval=args.max_interval,
        loop=args.loop,
        limit=args.limit,
    )


if __name__ == "__main__":
    asyncio.run(main())
