from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device
from app.schemas import DeviceCreate, DeviceCreated, DeviceOut
from app.security import hash_key, new_device_key, require_admin

router = APIRouter(prefix="/devices", tags=["devices"], dependencies=[Depends(require_admin)])


def get_device_or_404(db: Session, device_id: int) -> Device:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    return device


@router.post("", response_model=DeviceCreated, status_code=status.HTTP_201_CREATED)
def register_device(payload: DeviceCreate, db: Session = Depends(get_db)) -> DeviceCreated:
    if db.scalar(select(Device).where(Device.name == payload.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A device with this name already exists")
    key = new_device_key()
    device = Device(name=payload.name, location=payload.location, api_key_hash=hash_key(key))
    db.add(device)
    db.commit()
    db.refresh(device)
    return DeviceCreated(**DeviceOut.model_validate(device).model_dump(), api_key=key)


@router.get("", response_model=list[DeviceOut])
def list_devices(db: Session = Depends(get_db)) -> list[Device]:
    return list(db.scalars(select(Device).order_by(Device.id)))


@router.post("/{device_id}/rotate-key", response_model=DeviceCreated)
def rotate_key(device_id: int, db: Session = Depends(get_db)) -> DeviceCreated:
    device = get_device_or_404(db, device_id)
    key = new_device_key()
    device.api_key_hash = hash_key(key)
    db.commit()
    return DeviceCreated(**DeviceOut.model_validate(device).model_dump(), api_key=key)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(device_id: int, db: Session = Depends(get_db)) -> None:
    db.delete(get_device_or_404(db, device_id))
    db.commit()
