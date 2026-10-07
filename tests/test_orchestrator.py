from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from orchestrator_service.main import app
from orchestrator_service.database import Base, get_db
import orchestrator_service.main as orchestrator_main


SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

class FakeResponse:
    def __init__(self, status_code, data=None):
        self.status_code = status_code
        self._data = data or {}

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._data

def test_saga_success(monkeypatch):

    def fake_post(url, json):

        if url == "http://localhost:8001/create":
            return FakeResponse(
                200,
                {
                    "id": 1,
                    "status": "PENDING"
                }
            )

        if url == "http://localhost:8002/reserve":
            return FakeResponse(200)

        if url == "http://localhost:8003/pay":
            return FakeResponse(200)

    def fake_put(url, json):
        if url == "http://localhost:8001/orders/status":
            return FakeResponse(200)

    monkeypatch.setattr(
        orchestrator_main,
        "post_with_retry",
        fake_post
    )

    monkeypatch.setattr(
        orchestrator_main,
        "put_with_retry",
        fake_put
    )

    response = client.post(
        "/saga",
        json={
            "product_id": 1,
            "quantity": 2,
            "price": 100.0,
            "account_id": 1
        }
    )

    assert response.status_code == 200
    assert response.json()["status"] == "PAID"

    saga_id = response.json()["saga_id"]

    response = client.get("/sagas")
    sagas = response.json()

    saga = next(
        s for s in sagas
        if s["id"] == saga_id
    )

    assert saga["status"] == "COMPLETED"
    assert saga["current_step"] == "COMPLETED"

def test_order_creation_failure(monkeypatch):

    def fake_post(url, json):
        if url == "http://localhost:8001/create":
            return FakeResponse(500)

    monkeypatch.setattr(
        orchestrator_main,
        "post_with_retry",
        fake_post
    )

    response = client.post(
        "/saga",
        json={
            "product_id": 1,
            "quantity": 2,
            "price": 100.0,
            "account_id": 1
        }
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Order creation failed"

    sagas = client.get("/sagas").json()
    saga = sagas[-1]

    assert saga["status"] == "FAILED"
    assert saga["current_step"] == "ORDER_CREATION_FAILED"

def test_inventory_failure(monkeypatch):

    calls = []

    def fake_post(url, json):
        calls.append(url)

        if url == "http://localhost:8001/create":
            return FakeResponse(
                200,
                {
                    "id": 10,
                    "status": "PENDING"
                }
            )

        if url == "http://localhost:8002/reserve":
            return FakeResponse(400)

        if url == "http://localhost:8001/cancel":
            return FakeResponse(200)

    monkeypatch.setattr(
        orchestrator_main,
        "post_with_retry",
        fake_post
    )

    response = client.post(
        "/saga",
        json={
            "product_id": 1,
            "quantity": 100,
            "price": 100.0,
            "account_id": 1
        }
    )

    assert response.status_code == 400

    assert "http://localhost:8001/cancel" in calls

    sagas = client.get("/sagas").json()
    saga = sagas[-1]

    assert saga["status"] == "COMPENSATED"
    assert saga["current_step"] == "ORDER_CANCELLED"

def test_payment_failure(monkeypatch):

    calls = []

    def fake_post(url, json):
        calls.append(url)

        if url == "http://localhost:8001/create":
            return FakeResponse(
                200,
                {
                    "id": 20,
                    "status": "PENDING"
                }
            )

        if url == "http://localhost:8002/reserve":
            return FakeResponse(200)

        if url == "http://localhost:8003/pay":
            return FakeResponse(400)

        if url == "http://localhost:8002/release":
            return FakeResponse(200)

        if url == "http://localhost:8001/cancel":
            return FakeResponse(200)

    monkeypatch.setattr(
        orchestrator_main,
        "post_with_retry",
        fake_post
    )

    response = client.post(
        "/saga",
        json={
            "product_id": 1,
            "quantity": 2,
            "price": 100.0,
            "account_id": 1
        }
    )

    assert response.status_code == 400

    assert "http://localhost:8003/pay" in calls
    assert "http://localhost:8002/release" in calls
    assert "http://localhost:8001/cancel" in calls

    # Proveri i redosled kompenzacija
    release_index = calls.index(
        "http://localhost:8002/release"
    )

    cancel_index = calls.index(
        "http://localhost:8001/cancel"
    )

    assert release_index < cancel_index

    sagas = client.get("/sagas").json()
    saga = sagas[-1]

    assert saga["status"] == "COMPENSATED"
    assert saga["current_step"] == "COMPENSATED"

def test_status_update_failure(monkeypatch):

    calls = []

    def fake_post(url, json):
        calls.append(url)

        if url == "http://localhost:8001/create":
            return FakeResponse(
                200,
                {
                    "id": 30,
                    "status": "PENDING"
                }
            )

        if url == "http://localhost:8002/reserve":
            return FakeResponse(200)

        if url == "http://localhost:8003/pay":
            return FakeResponse(200)

        if url == "http://localhost:8003/refund":
            return FakeResponse(200)

        if url == "http://localhost:8002/release":
            return FakeResponse(200)

        if url == "http://localhost:8001/cancel":
            return FakeResponse(200)

    def fake_put(url, json):
        return FakeResponse(500)

    monkeypatch.setattr(
        orchestrator_main,
        "post_with_retry",
        fake_post
    )

    monkeypatch.setattr(
        orchestrator_main,
        "put_with_retry",
        fake_put
    )

    response = client.post(
        "/saga",
        json={
            "product_id": 1,
            "quantity": 2,
            "price": 100.0,
            "account_id": 1
        }
    )

    assert response.status_code == 400

    assert "http://localhost:8003/refund" in calls
    assert "http://localhost:8002/release" in calls
    assert "http://localhost:8001/cancel" in calls

    refund_index = calls.index(
        "http://localhost:8003/refund"
    )

    release_index = calls.index(
        "http://localhost:8002/release"
    )

    cancel_index = calls.index(
        "http://localhost:8001/cancel"
    )

    assert refund_index < release_index < cancel_index

    sagas = client.get("/sagas").json()
    saga = sagas[-1]

    assert saga["status"] == "COMPENSATED"
    assert saga["current_step"] == "COMPENSATED"

def test_inventory_failure_cancel_failure(monkeypatch):

    def fake_post(url, json):

        if url == "http://localhost:8001/create":
            return FakeResponse(
                200,
                {
                    "id": 40,
                    "status": "PENDING"
                }
            )

        if url == "http://localhost:8002/reserve":
            return FakeResponse(400)

        if url == "http://localhost:8001/cancel":
            return FakeResponse(500)

    monkeypatch.setattr(
        orchestrator_main,
        "post_with_retry",
        fake_post
    )

    response = client.post(
        "/saga",
        json={
            "product_id": 1,
            "quantity": 2,
            "price": 100.0,
            "account_id": 1
        }
    )

    assert response.status_code == 500

    sagas = client.get("/sagas").json()
    saga = sagas[-1]

    assert saga["status"] == "COMPENSATION_FAILED"
    assert saga["current_step"] == "ORDER_CANCEL_FAILED"

def test_payment_failure_release_failure(monkeypatch):

    def fake_post(url, json):

        if url == "http://localhost:8001/create":
            return FakeResponse(
                200,
                {
                    "id": 50,
                    "status": "PENDING"
                }
            )

        if url == "http://localhost:8002/reserve":
            return FakeResponse(200)

        if url == "http://localhost:8003/pay":
            return FakeResponse(400)

        if url == "http://localhost:8002/release":
            return FakeResponse(500)

    monkeypatch.setattr(
        orchestrator_main,
        "post_with_retry",
        fake_post
    )

    response = client.post(
        "/saga",
        json={
            "product_id": 1,
            "quantity": 2,
            "price": 100.0,
            "account_id": 1
        }
    )

    assert response.status_code == 500

    sagas = client.get("/sagas").json()
    saga = sagas[-1]

    assert saga["status"] == "COMPENSATION_FAILED"
    assert saga["current_step"] == "INVENTORY_RELEASE_FAILED"


def test_payment_failure_cancel_failure(monkeypatch):

    calls = []

    def fake_post(url, json):
        calls.append(url)

        if url == "http://localhost:8001/create":
            return FakeResponse(
                200,
                {
                    "id": 60,
                    "status": "PENDING"
                }
            )

        if url == "http://localhost:8002/reserve":
            return FakeResponse(200)

        if url == "http://localhost:8003/pay":
            return FakeResponse(400)

        if url == "http://localhost:8002/release":
            return FakeResponse(200)

        if url == "http://localhost:8001/cancel":
            return FakeResponse(500)

    monkeypatch.setattr(
        orchestrator_main,
        "post_with_retry",
        fake_post
    )

    response = client.post(
        "/saga",
        json={
            "product_id": 1,
            "quantity": 2,
            "price": 100.0,
            "account_id": 1
        }
    )

    assert response.status_code == 500

    assert "http://localhost:8002/release" in calls
    assert "http://localhost:8001/cancel" in calls

    sagas = client.get("/sagas").json()
    saga = sagas[-1]

    assert saga["status"] == "COMPENSATION_FAILED"
    assert saga["current_step"] == "ORDER_CANCEL_FAILED"

def test_status_update_failure_refund_failure(monkeypatch):

    def fake_post(url, json):

        if url == "http://localhost:8001/create":
            return FakeResponse(
                200,
                {
                    "id": 70,
                    "status": "PENDING"
                }
            )

        if url == "http://localhost:8002/reserve":
            return FakeResponse(200)

        if url == "http://localhost:8003/pay":
            return FakeResponse(200)

        if url == "http://localhost:8003/refund":
            return FakeResponse(500)

    def fake_put(url, json):
        return FakeResponse(500)

    monkeypatch.setattr(
        orchestrator_main,
        "post_with_retry",
        fake_post
    )

    monkeypatch.setattr(
        orchestrator_main,
        "put_with_retry",
        fake_put
    )

    response = client.post(
        "/saga",
        json={
            "product_id": 1,
            "quantity": 2,
            "price": 100.0,
            "account_id": 1
        }
    )

    assert response.status_code == 500

    sagas = client.get("/sagas").json()
    saga = sagas[-1]

    assert saga["status"] == "COMPENSATION_FAILED"
    assert saga["current_step"] == "PAYMENT_REFUND_FAILED"

def test_status_update_failure_release_failure(monkeypatch):

    calls = []

    def fake_post(url, json):
        calls.append(url)

        if url == "http://localhost:8001/create":
            return FakeResponse(
                200,
                {
                    "id": 80,
                    "status": "PENDING"
                }
            )

        if url == "http://localhost:8002/reserve":
            return FakeResponse(200)

        if url == "http://localhost:8003/pay":
            return FakeResponse(200)

        if url == "http://localhost:8003/refund":
            return FakeResponse(200)

        if url == "http://localhost:8002/release":
            return FakeResponse(500)

    def fake_put(url, json):
        return FakeResponse(500)

    monkeypatch.setattr(
        orchestrator_main,
        "post_with_retry",
        fake_post
    )

    monkeypatch.setattr(
        orchestrator_main,
        "put_with_retry",
        fake_put
    )

    response = client.post(
        "/saga",
        json={
            "product_id": 1,
            "quantity": 2,
            "price": 100.0,
            "account_id": 1
        }
    )

    assert response.status_code == 500

    assert "http://localhost:8003/refund" in calls
    assert "http://localhost:8002/release" in calls

    sagas = client.get("/sagas").json()
    saga = sagas[-1]

    assert saga["status"] == "COMPENSATION_FAILED"
    assert saga["current_step"] == "INVENTORY_RELEASE_FAILED"

def test_status_update_failure_cancel_failure(monkeypatch):

    calls = []

    def fake_post(url, json):
        calls.append(url)

        if url == "http://localhost:8001/create":
            return FakeResponse(
                200,
                {
                    "id": 90,
                    "status": "PENDING"
                }
            )

        if url == "http://localhost:8002/reserve":
            return FakeResponse(200)

        if url == "http://localhost:8003/pay":
            return FakeResponse(200)

        if url == "http://localhost:8003/refund":
            return FakeResponse(200)

        if url == "http://localhost:8002/release":
            return FakeResponse(200)

        if url == "http://localhost:8001/cancel":
            return FakeResponse(500)

    def fake_put(url, json):
        return FakeResponse(500)

    monkeypatch.setattr(
        orchestrator_main,
        "post_with_retry",
        fake_post
    )

    monkeypatch.setattr(
        orchestrator_main,
        "put_with_retry",
        fake_put
    )

    response = client.post(
        "/saga",
        json={
            "product_id": 1,
            "quantity": 2,
            "price": 100.0,
            "account_id": 1
        }
    )

    assert response.status_code == 500

    assert "http://localhost:8003/refund" in calls
    assert "http://localhost:8002/release" in calls
    assert "http://localhost:8001/cancel" in calls

    sagas = client.get("/sagas").json()
    saga = sagas[-1]

    assert saga["status"] == "COMPENSATION_FAILED"
    assert saga["current_step"] == "ORDER_CANCEL_FAILED"
