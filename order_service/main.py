from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
import httpx

from .database import engine, get_db
from . import models, schemas


models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Order Service")


@app.get("/")
def root():
    return {"message": "Order Service radi"}


@app.post("/create", response_model=schemas.OrderResponse)
def create_order(
    order: schemas.OrderCreate,
    db: Session = Depends(get_db)
):
    # Proveri da li je ova Saga vec kreirala order
    existing_order = db.query(models.Order).filter(
        models.Order.saga_id == order.saga_id
    ).first()

    # Ako jeste, samo vrati postojeci order
    if existing_order:
        return existing_order

    # Ako nije, kreiraj novi order
    new_order = models.Order(
        saga_id=order.saga_id,
        product_id=order.product_id,
        quantity=order.quantity,
        price=order.price,
        status="PENDING"
    )

    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    return new_order

@app.get("/orders", response_model=list[schemas.OrderResponse])
def get_orders(db: Session = Depends(get_db)):
    orders = db.query(models.Order).all()
    return orders

@app.put("/orders/status", response_model=schemas.OrderResponse)
def update_order_status(
    order_update: schemas.OrderUpdate,
    db: Session = Depends(get_db)
):
    order = db.query(models.Order).filter(
        models.Order.id == order_update.id
    ).first()

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    order.status = order_update.status

    db.commit()
    db.refresh(order)

    return order

@app.post("/cancel", response_model=schemas.OrderResponse)
def cancel_order(
    request: schemas.CancelOrderRequest,
    db: Session = Depends(get_db)
):
    order = db.query(models.Order).filter(
        models.Order.id == request.order_id
    ).first()

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    order.status = "CANCELLED"

    db.commit()
    db.refresh(order)

    return order