from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from payment_service.main import app
from payment_service.database import Base, get_db


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


def test_root():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "message": "Payment Service radi"
    }


def test_create_account():
    response = client.post(
        "/accounts",
        json={
            "client_id": 1,
            "balance": 1000.0
        }
    )

    assert response.status_code == 200

    data = response.json()

    assert data["client_id"] == 1
    assert data["balance"] == 1000.0


def test_pay():
    account_response = client.post(
        "/accounts",
        json={
            "client_id": 2,
            "balance": 1000.0
        }
    )

    account_id = account_response.json()["id"]

    response = client.post(
        "/pay",
        json={
            "saga_id": 1,
            "order_id": 1,
            "account_id": account_id,
            "amount": 200.0
        }
    )

    assert response.status_code == 200

    data = response.json()

    assert data["saga_id"] == 1
    assert data["amount"] == 200.0
    assert data["status"] == "COMPLETED"

    # Proverimo da li je novac skinut
    account_response = client.get(
        f"/accounts/{account_id}"
    )

    assert account_response.json()["balance"] == 800.0


def test_pay_is_idempotent():
    account_response = client.post(
        "/accounts",
        json={
            "client_id": 3,
            "balance": 1000.0
        }
    )

    account_id = account_response.json()["id"]

    request_data = {
        "saga_id": 2,
        "order_id": 2,
        "account_id": account_id,
        "amount": 200.0
    }

    response1 = client.post(
        "/pay",
        json=request_data
    )

    response2 = client.post(
        "/pay",
        json=request_data
    )

    assert response1.status_code == 200
    assert response2.status_code == 200

    # Oba poziva moraju vratiti isti Payment
    assert response1.json()["id"] == response2.json()["id"]

    account_response = client.get(
        f"/accounts/{account_id}"
    )

    # 1000 - 200 = 800
    # Ne sme da bude 600
    assert account_response.json()["balance"] == 800.0


def test_insufficient_funds():
    account_response = client.post(
        "/accounts",
        json={
            "client_id": 4,
            "balance": 100.0
        }
    )

    account_id = account_response.json()["id"]

    response = client.post(
        "/pay",
        json={
            "saga_id": 3,
            "order_id": 3,
            "account_id": account_id,
            "amount": 500.0
        }
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient funds"

    # Stanje mora ostati nepromenjeno
    account_response = client.get(
        f"/accounts/{account_id}"
    )

    assert account_response.json()["balance"] == 100.0


def test_refund():
    account_response = client.post(
        "/accounts",
        json={
            "client_id": 5,
            "balance": 1000.0
        }
    )

    account_id = account_response.json()["id"]

    client.post(
        "/pay",
        json={
            "saga_id": 4,
            "order_id": 4,
            "account_id": account_id,
            "amount": 300.0
        }
    )

    # Sada je balance 700
    refund_response = client.post(
        "/refund",
        json={
            "saga_id": 4
        }
    )

    assert refund_response.status_code == 200
    assert refund_response.json()["status"] == "REFUNDED"

    account_response = client.get(
        f"/accounts/{account_id}"
    )

    # Refund mora vratiti 300
    assert account_response.json()["balance"] == 1000.0


def test_refund_is_idempotent():
    account_response = client.post(
        "/accounts",
        json={
            "client_id": 6,
            "balance": 1000.0
        }
    )

    account_id = account_response.json()["id"]

    client.post(
        "/pay",
        json={
            "saga_id": 5,
            "order_id": 5,
            "account_id": account_id,
            "amount": 300.0
        }
    )

    response1 = client.post(
        "/refund",
        json={
            "saga_id": 5
        }
    )

    response2 = client.post(
        "/refund",
        json={
            "saga_id": 5
        }
    )

    assert response1.status_code == 200
    assert response2.status_code == 200

    assert response1.json()["status"] == "REFUNDED"
    assert response2.json()["status"] == "REFUNDED"

    account_response = client.get(
        f"/accounts/{account_id}"
    )

    # Mora biti 1000, a ne 1300
    assert account_response.json()["balance"] == 1000.0