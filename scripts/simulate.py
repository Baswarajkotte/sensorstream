"""Simulate IoT devices sending readings to SensorStream.

Registers a few devices, adds alert rules, then sends 24 hours of readings
(every 2 minutes) with daily cycles, noise and a few injected spikes.

    python scripts/simulate.py --url http://localhost:8000 --admin-key dev-admin-key
"""

import argparse
import math
import random
from datetime import datetime, timedelta, timezone

import httpx

DEVICES = [
    ("fibre-sensor-01", "Hubli warehouse"),
    ("fibre-sensor-02", "Bengaluru lab"),
]


def reading_series(start: datetime, points: int, step: timedelta, seed: int) -> list[dict]:
    rng = random.Random(seed)
    spikes = set(rng.sample(range(50, points), 4))
    out = []
    for i in range(points):
        ts = start + i * step
        hour = ts.hour + ts.minute / 60
        temperature = 27 + 4 * math.sin((hour - 9) / 24 * 2 * math.pi) + rng.gauss(0, 0.3)
        humidity = 60 - 10 * math.sin((hour - 9) / 24 * 2 * math.pi) + rng.gauss(0, 1.0)
        moisture = 11.5 + rng.gauss(0, 0.15)
        if i in spikes:
            temperature += rng.choice([9, -8])
            moisture += 2.5
        out += [
            {"metric": "temperature_c", "value": round(temperature, 2), "ts": ts.isoformat()},
            {"metric": "humidity_pct", "value": round(humidity, 2), "ts": ts.isoformat()},
            {"metric": "moisture_pct", "value": round(moisture, 2), "ts": ts.isoformat()},
        ]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--admin-key", default="dev-admin-key")
    parser.add_argument("--hours", type=int, default=24)
    args = parser.parse_args()

    admin = {"X-API-Key": args.admin_key}
    with httpx.Client(base_url=args.url, timeout=30) as client:
        client.post("/rules", headers=admin, json={"metric": "temperature_c", "operator": "gt", "threshold": 34})
        client.post("/rules", headers=admin, json={"metric": "moisture_pct", "operator": "gt", "threshold": 13})

        start = datetime.now(timezone.utc) - timedelta(hours=args.hours)
        points = args.hours * 30  # one reading every 2 minutes
        for seed, (name, location) in enumerate(DEVICES):
            res = client.post("/devices", headers=admin, json={"name": name, "location": location})
            if res.status_code == 409:
                print(f"{name} already exists; skipping")
                continue
            res.raise_for_status()
            device_key = {"X-API-Key": res.json()["api_key"]}

            readings = reading_series(start, points, timedelta(minutes=2), seed)
            sent = alerts = 0
            for i in range(0, len(readings), 500):
                batch = client.post("/ingest", headers=device_key, json={"readings": readings[i : i + 500]})
                batch.raise_for_status()
                sent += batch.json()["accepted"]
                alerts += batch.json()["alerts_triggered"]
            print(f"{name}: sent {sent} readings, {alerts} alerts triggered")

    print(f"Open {args.url}/ and enter the admin key to see the dashboard.")


if __name__ == "__main__":
    main()
