from datetime import datetime, timedelta, timezone

from tests.conftest import ADMIN


def series(values, metric="temperature_c", minutes=1):
    start = datetime.now(timezone.utc) - timedelta(minutes=len(values) * minutes)
    return [
        {"metric": metric, "value": v, "ts": (start + timedelta(minutes=i * minutes)).isoformat()}
        for i, v in enumerate(values)
    ]


def test_admin_key_required(client):
    assert client.get("/devices").status_code == 401
    assert client.get("/devices", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/devices", headers=ADMIN).status_code == 200


def test_register_device_returns_key_once(client, device):
    devices = client.get("/devices", headers=ADMIN).json()
    assert devices[0]["name"] == "sensor-1"
    assert "api_key" not in devices[0]
    dup = client.post("/devices", headers=ADMIN, json={"name": "sensor-1"})
    assert dup.status_code == 409


def test_ingest_needs_device_key(client, device):
    body = {"readings": series([20.0])}
    assert client.post("/ingest", json=body).status_code == 401
    assert client.post("/ingest", headers=ADMIN, json=body).status_code == 401
    res = client.post("/ingest", headers=device["headers"], json=body)
    assert res.status_code == 202
    assert res.json() == {"accepted": 1, "alerts_triggered": 0}


def test_ingest_validates_readings(client, device):
    bad_metric = {"readings": [{"metric": "Bad Metric!", "value": 1}]}
    assert client.post("/ingest", headers=device["headers"], json=bad_metric).status_code == 422
    empty = {"readings": []}
    assert client.post("/ingest", headers=device["headers"], json=empty).status_code == 422


def test_rotating_key_revokes_old_key(client, device):
    new = client.post(f"/devices/{device['id']}/rotate-key", headers=ADMIN).json()["api_key"]
    body = {"readings": series([1.0])}
    assert client.post("/ingest", headers=device["headers"], json=body).status_code == 401
    assert client.post("/ingest", headers={"X-API-Key": new}, json=body).status_code == 202


def test_threshold_rules_create_alerts(client, device):
    client.post("/rules", headers=ADMIN, json={"metric": "temperature_c", "operator": "gt", "threshold": 30})
    client.post(
        "/rules",
        headers=ADMIN,
        json={"device_id": device["id"], "metric": "temperature_c", "operator": "lt", "threshold": 5},
    )
    res = client.post("/ingest", headers=device["headers"], json={"readings": series([25, 31, 2, 28])})
    assert res.json()["alerts_triggered"] == 2

    alerts = client.get("/alerts", headers=ADMIN, params={"unacknowledged": True}).json()
    assert sorted(a["value"] for a in alerts) == [2.0, 31.0]

    client.post(f"/alerts/{alerts[0]['id']}/ack", headers=ADMIN)
    remaining = client.get("/alerts", headers=ADMIN, params={"unacknowledged": True}).json()
    assert len(remaining) == 1


def test_stats_and_metrics(client, device):
    values = [10.0] * 30 + [20.0] * 30
    client.post("/ingest", headers=device["headers"], json={"readings": series(values)})

    assert client.get(f"/devices/{device['id']}/metrics", headers=ADMIN).json() == ["temperature_c"]

    res = client.get(
        f"/devices/{device['id']}/stats",
        headers=ADMIN,
        params={"metric": "temperature_c", "bucket": "1h", "hours": 2},
    )
    assert res.status_code == 200
    points = res.json()["points"]
    assert sum(p["count"] for p in points) == 60
    assert min(p["min"] for p in points) == 10.0
    assert max(p["max"] for p in points) == 20.0


def test_stats_rejects_unknown_bucket(client, device):
    res = client.get(
        f"/devices/{device['id']}/stats", headers=ADMIN, params={"metric": "x", "bucket": "7min"}
    )
    assert res.status_code == 422


def test_anomaly_endpoint_finds_spike(client, device):
    values = [20 + (i % 3) * 0.1 for i in range(40)]
    values[30] = 45.0
    client.post("/ingest", headers=device["headers"], json={"readings": series(values)})
    res = client.get(
        f"/devices/{device['id']}/anomalies",
        headers=ADMIN,
        params={"metric": "temperature_c", "window": 10},
    ).json()
    assert res["checked"] == 40
    assert [a["value"] for a in res["anomalies"]] == [45.0]


def test_csv_export(client, device):
    client.post("/ingest", headers=device["headers"], json={"readings": series([1.5, 2.5])})
    res = client.get(f"/devices/{device['id']}/export.csv", headers=ADMIN)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    lines = res.text.strip().splitlines()
    assert lines[0] == "timestamp,device,metric,value"
    assert len(lines) == 3


def test_unknown_device_is_404(client):
    assert client.get("/devices/999/stats", headers=ADMIN, params={"metric": "x"}).status_code == 404
