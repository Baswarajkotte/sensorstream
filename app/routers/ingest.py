from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Device, Reading
from app.schemas import IngestRequest, IngestResult
from app.security import require_device
from app.services import alerts

router = APIRouter(tags=["ingest"])


@router.post("/ingest", response_model=IngestResult, status_code=status.HTTP_202_ACCEPTED)
def ingest(
    payload: IngestRequest,
    device: Device = Depends(require_device),
    db: Session = Depends(get_db),
) -> IngestResult:
    """Devices push a batch of readings, authenticated with their own X-API-Key."""
    limit = get_settings().max_batch_size
    if len(payload.readings) > limit:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Send at most {limit} readings per batch"
        )
    now = datetime.now(timezone.utc)
    readings = [
        Reading(device_id=device.id, metric=r.metric, value=r.value, ts=r.ts or now)
        for r in payload.readings
    ]
    db.add_all(readings)
    triggered = alerts.evaluate(db, device.id, readings)
    device.last_seen_at = now
    db.commit()
    return IngestResult(accepted=len(readings), alerts_triggered=len(triggered))
