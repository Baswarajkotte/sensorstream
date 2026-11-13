"""Evaluate threshold rules against incoming readings."""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Alert, AlertRule, Reading


def breaches(rule: AlertRule, value: float) -> bool:
    if rule.operator == "gt":
        return value > rule.threshold
    if rule.operator == "lt":
        return value < rule.threshold
    return False


def evaluate(db: Session, device_id: int, readings: list[Reading]) -> list[Alert]:
    """Create an Alert for every reading that breaches an enabled rule."""
    metrics = {r.metric for r in readings}
    rules = db.scalars(
        select(AlertRule).where(
            AlertRule.enabled.is_(True),
            AlertRule.metric.in_(metrics),
            or_(AlertRule.device_id.is_(None), AlertRule.device_id == device_id),
        )
    ).all()
    if not rules:
        return []

    by_metric: dict[str, list[AlertRule]] = {}
    for rule in rules:
        by_metric.setdefault(rule.metric, []).append(rule)

    alerts = [
        Alert(
            rule_id=rule.id,
            device_id=device_id,
            metric=reading.metric,
            value=reading.value,
            threshold=rule.threshold,
            ts=reading.ts,
        )
        for reading in readings
        for rule in by_metric.get(reading.metric, [])
        if breaches(rule, reading.value)
    ]
    db.add_all(alerts)
    return alerts
