from fastapi import FastAPI, HTTPException
import httpx

from . import schemas

app = FastAPI(title="Saga Orchestrator Service")


@app.get("/")
def root():
    return {"message": "Saga Orchestrator Service radi"}


@app.post("/saga")
def start_saga(request: schemas.OrderSagaRequest):

    # 1. Kreiraj order
    order_response = httpx.post(
        "http://localhost:8001/orders",
        json={
            "product_id": request.product_id,
            "quantity": request.quantity,
            "price": request.price
        }
    )

    if not order_response.is_success:
        raise HTTPException(
            status_code=400,
            detail="Order creation failed"
        )

    order = order_response.json()
    order_id = order["id"]

    # 2. Rezervisi proizvod
    inventory_response = httpx.post(
        "http://localhost:8002/reserve",
        json={
            "product_id": request.product_id,
            "quantity": request.quantity
        }
    )

    if not inventory_response.is_success:

        # Kompenzacija za create order
        httpx.post(
            "http://localhost:8001/cancel",
            json={
                "order_id": order_id
            }
        )

        raise HTTPException(
            status_code=400,
            detail="Inventory reservation failed"
        )

    # 3. Izvrsi placanje
    payment_response = httpx.post(
        "http://localhost:8003/pay",
        json={
            "order_id": order_id,
            "account_id": request.account_id,
            "amount": request.price * request.quantity
        }
    )

    if not payment_response.is_success:

        # Kompenzacija za reserve
        httpx.post(
            "http://localhost:8002/release",
            json={
                "product_id": request.product_id,
                "quantity": request.quantity
            }
        )

        # Kompenzacija za create order
        httpx.post(
            "http://localhost:8001/cancel",
            json={
                "order_id": order_id
            }
        )

        raise HTTPException(
            status_code=400,
            detail="Payment failed"
        )

    # 4. Promeni status ordera na PAID
    status_response = httpx.put(
        "http://localhost:8001/orders/status",
        json={
            "id": order_id,
            "status": "PAID"
        }
    )

    return {
        "order_id": order_id,
        "status": "PAID"
    }