from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
import httpx

from . import schemas, models
from .database import engine, get_db


models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Saga Orchestrator Service")


@app.get("/")
def root():
    return {"message": "Saga Orchestrator Service radi"}


@app.post("/saga")
def start_saga(
    request: schemas.OrderSagaRequest,
    db: Session = Depends(get_db)
):

    # 0. Kreiraj Sagu
    saga = models.Saga(
        status="STARTED",
        current_step="STARTED"
    )

    db.add(saga)
    db.commit()
    db.refresh(saga)

    saga_id = saga.id

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
        saga.status = "FAILED"
        saga.current_step = "ORDER_CREATION_FAILED"
        db.commit()

        raise HTTPException(
            status_code=400,
            detail="Order creation failed"
        )

    order = order_response.json()
    order_id = order["id"]

    # Sacuvaj order_id i trenutno stanje Sage
    saga.order_id = order_id
    saga.status = "IN_PROGRESS"
    saga.current_step = "ORDER_CREATED"
    db.commit()

    # 2. Rezervisi proizvod
    inventory_response = httpx.post(
        "http://localhost:8002/reserve",
        json={
            "product_id": request.product_id,
            "quantity": request.quantity
        }
    )

    if not inventory_response.is_success:

        saga.status = "COMPENSATING"
        saga.current_step = "CANCELLING_ORDER"
        db.commit()

        # Kompenzacija za create order
        httpx.post(
            "http://localhost:8001/cancel",
            json={
                "order_id": order_id
            }
        )

        saga.status = "COMPENSATED"
        saga.current_step = "ORDER_CANCELLED"
        db.commit()

        raise HTTPException(
            status_code=400,
            detail="Inventory reservation failed"
        )

    saga.current_step = "INVENTORY_RESERVED"
    db.commit()

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

        saga.status = "COMPENSATING"
        saga.current_step = "RELEASING_INVENTORY"
        db.commit()

        # Kompenzacija za reserve
        httpx.post(
            "http://localhost:8002/release",
            json={
                "product_id": request.product_id,
                "quantity": request.quantity
            }
        )

        saga.current_step = "CANCELLING_ORDER"
        db.commit()

        # Kompenzacija za create order
        httpx.post(
            "http://localhost:8001/cancel",
            json={
                "order_id": order_id
            }
        )

        saga.status = "COMPENSATED"
        saga.current_step = "COMPENSATED"
        db.commit()

        raise HTTPException(
            status_code=400,
            detail="Payment failed"
        )

    saga.current_step = "PAYMENT_COMPLETED"
    db.commit()

    # 4. Promeni status ordera na PAID
    status_response = httpx.put(
        "http://localhost:8001/orders/status",
        json={
            "id": order_id,
            "status": "PAID"
        }
    )

    if not status_response.is_success:
        saga.status = "FAILED"
        saga.current_step = "ORDER_STATUS_UPDATE_FAILED"
        db.commit()

        raise HTTPException(
            status_code=400,
            detail="Order status update failed"
        )

    # Saga je uspesno zavrsena
    saga.status = "COMPLETED"
    saga.current_step = "COMPLETED"
    db.commit()

    return {
        "saga_id": saga_id,
        "order_id": order_id,
        "status": "PAID"
    }