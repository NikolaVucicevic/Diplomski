from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
import httpx

from .database import engine, get_db
from . import models, schemas


models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Order Service")


@app.get("/")
def root():
    return {"message": "Order Service radi"}


@app.post("/orders", response_model=schemas.OrderResponse)
def create_order(
    order: schemas.OrderCreate,
    db: Session = Depends(get_db)
):
    # 1. Kreiramo order
    new_order = models.Order(
        product_id=order.product_id,
        quantity=order.quantity,
        price=order.price,
        status="PENDING"
    )

    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    # 2. Pozivamo Inventory Service
    inventory_response = httpx.post(
        "http://localhost:8002/reserve",
        json={
            "product_id": order.product_id,
            "quantity": order.quantity
        }
    )

    # Ako rezervacija nije uspela
    if inventory_response.status_code != 200:
        new_order.status = "FAILED"
        db.commit()
        db.refresh(new_order)
        return new_order

    # Rezervacija uspela
    new_order.status = "RESERVED"
    db.commit()
    db.refresh(new_order)

    # 3. Pozivamo Payment Service
    payment_response = httpx.post(
        "http://localhost:8003/pay",
        json={
            "order_id": new_order.id,
            "amount": order.price * order.quantity
        }
    )

    # 4. Proveravamo rezultat plaćanja
    if payment_response.status_code == 200:
        new_order.status = "PAID"
    else:
        new_order.status = "PAYMENT_FAILED"

    db.commit()
    db.refresh(new_order)

    return new_order

@app.get("/orders", response_model=list[schemas.OrderResponse])
def get_orders(db: Session = Depends(get_db)):
    orders = db.query(models.Order).all()
    return orders