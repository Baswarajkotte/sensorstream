import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Alert, AlertRule, Reading
from app.routers.devices import get_device_or_404
from app.schemas import (
    AlertOut,
    AnomalyResponse,
    RuleCreate,
    RuleOut,
    StatsResponse,
)
from app.security import require_admin
from app.services.analytics import BUCKETS, bucket_stats, detect_anomalies, to_frame

router = APIRouter(tags=["analytics"], dependencies=[Depends(require_admin)])


def _load(
    db: Session, device_id: int, metric: str, hours: int
) -> list[tuple[datetime, float]]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    return list(
        db.execute(
            select(Reading.ts, Reading.value)
            .where(Reading.device_id == device_id, Reading.metric == metric, Reading.ts >= since)
            .order_by(Reading.ts)
        ).tuples()
    )


@router.get("/devices/{device_id}/metrics", response_model=list[str])
def list_metrics(device_id: int, db: Session = Depends(get_db)) -> list[str]:
    get_device_or_404(db, device_id)
    return list(
        db.scalars(
            select(Reading.metric).where(Reading.device_id == device_id).distinct().order_by(Reading.metric)
        )
    )


@router.get("/devices/{device_id}/stats", response_model=StatsResponse)
def stats(
    device_id: int,
    metric: str,
    bucket: str = Query("1h", description=f"One of: {', '.join(BUCKETS)}"),
    hours: int = Query(24, ge=1, le=24 * 90),
    db: Session = Depends(get_db),
) -> StatsResponse:
    get_device_or_404(db, device_id)
    if bucket not in BUCKETS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"bucket must be one of {list(BUCKETS)}")
    points = bucket_stats(to_frame(_load(db, device_id, metric, hours)), bucket)
    return StatsResponse(device_id=device_id, metric=metric, bucket=bucket, points=points)


@router.get("/devices/{device_id}/anomalies", response_model=AnomalyResponse)
def anomalies(
    device_id: int,
    metric: str,
    window: int = Query(20, ge=3, le=500),
    threshold: float = Query(3.0, gt=0, le=10),
    hours: int = Query(24, ge=1, le=24 * 90),
    db: Session = Depends(get_db),
) -> AnomalyResponse:
    get_device_or_404(db, device_id)
    df = to_frame(_load(db, device_id, metric, hours))
    return AnomalyResponse(
        device_id=device_id,
        metric=metric,
        window=window,
        threshold=threshold,
        checked=len(df),
        anomalies=detect_anomalies(df, window, threshold),
    )


@router.get("/devices/{device_id}/export.csv")
def export_csv(
    device_id: int,
    metric: str | None = None,
    hours: int = Query(24, ge=1, le=24 * 90),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    device = get_device_or_404(db, device_id)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = select(Reading).where(Reading.device_id == device_id, Reading.ts >= since)
    if metric:
        stmt = stmt.where(Reading.metric == metric)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["timestamp", "device", "metric", "value"])
    for r in db.scalars(stmt.order_by(Reading.ts)):
        writer.writerow([r.ts.isoformat(), device.name, r.metric, r.value])
    buffer.seek(0)
    filename = f"{device.name}-{metric or 'all'}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(payload: RuleCreate, db: Session = Depends(get_db)) -> AlertRule:
    if payload.device_id is not None:
        get_device_or_404(db, payload.device_id)
    rule = AlertRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/rules", response_model=list[RuleOut])
def list_rules(db: Session = Depends(get_db)) -> list[AlertRule]:
    return list(db.scalars(select(AlertRule).order_by(AlertRule.id)))


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, db: Session = Depends(get_db)) -> None:
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    db.delete(rule)
    db.commit()


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    device_id: int | None = None,
    unacknowledged: bool = False,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[Alert]:
    stmt = select(Alert)
    if device_id is not None:
        stmt = stmt.where(Alert.device_id == device_id)
    if unacknowledged:
        stmt = stmt.where(Alert.acknowledged.is_(False))
    return list(db.scalars(stmt.order_by(Alert.id.desc()).limit(limit)))


@router.post("/alerts/{alert_id}/ack", response_model=AlertOut)
def acknowledge(alert_id: int, db: Session = Depends(get_db)) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    alert.acknowledged = True
    db.commit()
    return alert
