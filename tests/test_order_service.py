from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from order_service.main import app
from order_service.database import Base, get_db


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
        "message": "Order Service radi"
    }

def test_create_order():
    response = client.post(
        "/create",
        json={
            "saga_id": 1,
            "product_id": 10,
            "quantity": 2,
            "price": 100.0
        }
    )

    assert response.status_code == 200

    data = response.json()

    assert data["saga_id"] == 1
    assert data["product_id"] == 10
    assert data["quantity"] == 2
    assert data["price"] == 100.0
    assert data["status"] == "PENDING"

def test_create_order_is_idempotent():
    request_data = {
        "saga_id": 2,
        "product_id": 20,
        "quantity": 3,
        "price": 200.0
    }

    response1 = client.post(
        "/create",
        json=request_data
    )

    response2 = client.post(
        "/create",
        json=request_data
    )

    assert response1.status_code == 200
    assert response2.status_code == 200

    order1 = response1.json()
    order2 = response2.json()

    assert order1["id"] == order2["id"]

    response = client.get("/orders")

    orders = response.json()

    orders_for_saga = [
        order for order in orders
        if order["saga_id"] == 2
    ]

    assert len(orders_for_saga) == 1

def test_cancel_order():
    create_response = client.post(
        "/create",
        json={
            "saga_id": 3,
            "product_id": 30,
            "quantity": 1,
            "price": 300.0
        }
    )

    order_id = create_response.json()["id"]

    cancel_response = client.post(
        "/cancel",
        json={
            "order_id": order_id
        }
    )

    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "CANCELLED"

def test_cancel_order_is_idempotent():
    create_response = client.post(
        "/create",
        json={
            "saga_id": 4,
            "product_id": 40,
            "quantity": 1,
            "price": 400.0
        }
    )

    order_id = create_response.json()["id"]

    response1 = client.post(
        "/cancel",
        json={
            "order_id": order_id
        }
    )

    response2 = client.post(
        "/cancel",
        json={
            "order_id": order_id
        }
    )

    assert response1.status_code == 200
    assert response2.status_code == 200

    assert response1.json()["status"] == "CANCELLED"
    assert response2.json()["status"] == "CANCELLED"

def test_update_order_status():
    create_response = client.post(
        "/create",
        json={
            "saga_id": 5,
            "product_id": 50,
            "quantity": 2,
            "price": 500.0
        }
    )

    order_id = create_response.json()["id"]

    response = client.put(
        "/orders/status",
        json={
            "id": order_id,
            "status": "PAID"
        }
    )

    assert response.status_code == 200
    assert response.json()["status"] == "PAID"