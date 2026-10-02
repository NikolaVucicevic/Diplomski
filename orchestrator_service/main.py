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

    if order_response.status_code != 200:
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

    if inventory_response.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail="Inventory reservation failed"
        )

    # 3. Izvrsi placanje
    payment_response = httpx.post(
        "http://localhost:8003/pay",
        json={
            "order_id": order_id,
            "amount": request.price * request.quantity
        }
    )

    if payment_response.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail="Payment failed"
        )

    # 4. Promeni status ordera na PAID
    httpx.put(
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