from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from inventory_service.main import app
from inventory_service.database import Base, get_db


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
        "message": "Inventory Service radi"
    }


def test_create_product():
    response = client.post(
        "/products",
        json={
            "name": "Laptop",
            "quantity": 10
        }
    )

    assert response.status_code == 200

    data = response.json()

    assert data["name"] == "Laptop"
    assert data["quantity"] == 10


def test_reserve_product():
    product_response = client.post(
        "/products",
        json={
            "name": "Monitor",
            "quantity": 10
        }
    )

    product_id = product_response.json()["id"]

    response = client.post(
        "/reserve",
        json={
            "saga_id": 1,
            "product_id": product_id,
            "quantity": 3
        }
    )

    assert response.status_code == 200
    assert response.json()["remaining_quantity"] == 7


def test_reserve_is_idempotent():
    product_response = client.post(
        "/products",
        json={
            "name": "Keyboard",
            "quantity": 10
        }
    )

    product_id = product_response.json()["id"]

    request_data = {
        "saga_id": 2,
        "product_id": product_id,
        "quantity": 3
    }

    response1 = client.post(
        "/reserve",
        json=request_data
    )

    response2 = client.post(
        "/reserve",
        json=request_data
    )

    assert response1.status_code == 200
    assert response2.status_code == 200

    # Proveravamo trenutno stanje proizvoda
    products_response = client.get("/products")

    products = products_response.json()

    product = next(
        p for p in products
        if p["id"] == product_id
    )

    # 10 - 3 = 7, a ne 10 - 3 - 3 = 4
    assert product["quantity"] == 7


def test_release_product():
    product_response = client.post(
        "/products",
        json={
            "name": "Mouse",
            "quantity": 10
        }
    )

    product_id = product_response.json()["id"]

    client.post(
        "/reserve",
        json={
            "saga_id": 3,
            "product_id": product_id,
            "quantity": 4
        }
    )

    response = client.post(
        "/release",
        json={
            "saga_id": 3
        }
    )

    assert response.status_code == 200
    assert response.json()["quantity"] == 10


def test_release_is_idempotent():
    product_response = client.post(
        "/products",
        json={
            "name": "Headphones",
            "quantity": 10
        }
    )

    product_id = product_response.json()["id"]

    client.post(
        "/reserve",
        json={
            "saga_id": 4,
            "product_id": product_id,
            "quantity": 4
        }
    )

    response1 = client.post(
        "/release",
        json={
            "saga_id": 4
        }
    )

    response2 = client.post(
        "/release",
        json={
            "saga_id": 4
        }
    )

    assert response1.status_code == 200
    assert response2.status_code == 200

    products_response = client.get("/products")
    products = products_response.json()

    product = next(
        p for p in products
        if p["id"] == product_id
    )

    # Mora ostati 10, a ne 14
    assert product["quantity"] == 10


def test_not_enough_stock():
    product_response = client.post(
        "/products",
        json={
            "name": "Phone",
            "quantity": 2
        }
    )

    product_id = product_response.json()["id"]

    response = client.post(
        "/reserve",
        json={
            "saga_id": 5,
            "product_id": product_id,
            "quantity": 10
        }
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Not enough products in stock"