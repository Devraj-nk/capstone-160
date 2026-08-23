from __future__ import annotations

import argparse
import asyncio

import httpx


async def main() -> None:
    parser = argparse.ArgumentParser(description="Demo consumer that pulls from queue and prints")
    parser.add_argument("--queue-url", default="http://127.0.0.1:8000/queue/dequeue")
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument(
        "--max-messages",
        type=int,
        default=0,
        help="Stop after printing N messages (0 = run forever)",
    )
    args = parser.parse_args()

    if args.interval <= 0:
        raise SystemExit("--interval must be > 0")
    if args.max_messages < 0:
        raise SystemExit("--max-messages must be >= 0")

    printed = 0

    async with httpx.AsyncClient(timeout=5.0) as client:
        while True:
            try:
                r = await client.post(args.queue_url)
                r.raise_for_status()
                body = r.json()
                item = body.get("item")
                if item:
                    payload = item.get("payload", {})

                    metadata = payload.get("metadata") or {}
                    attributes = metadata.get("attributes") or {}
                    tweet_id = attributes.get("tweet_id")
                    label = attributes.get("label")

                    print(
                        f"dequeued id={payload.get('id')} tweet_id={tweet_id} label={label} text={payload.get('text')}"
                    )

                    printed += 1
                    if args.max_messages and printed >= args.max_messages:
                        return
            except httpx.HTTPError as e:
                print(f"consumer error: {e}")

            await asyncio.sleep(args.interval)


if __name__ == "__main__":
    asyncio.run(main())
