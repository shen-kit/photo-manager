from __future__ import annotations

import os
import time

from redis import Redis


def main() -> None:
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    worker_name = os.getenv("WORKER_NAME", "default")
    client = Redis.from_url(redis_url)

    while True:
        try:
            client.ping()
            print(f"[worker:{worker_name}] idle, redis reachable")
        except Exception as exc:  # pragma: no cover - bootstrap logging only
            print(f"[worker:{worker_name}] redis unavailable: {exc}")
        time.sleep(10)


if __name__ == "__main__":
    main()
