import os
import tempfile

_db_file = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file}"
os.environ["ADMIN_API_KEY"] = "test-admin"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

ADMIN = {"X-API-Key": "test-admin"}


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def device(client):
    res = client.post("/devices", headers=ADMIN, json={"name": "sensor-1", "location": "lab"})
    body = res.json()
    return {"id": body["id"], "headers": {"X-API-Key": body["api_key"]}}
