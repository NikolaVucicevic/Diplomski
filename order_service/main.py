from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

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

    # Ako jeste, vrati postojeci order
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

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        # Moguce je da je drugi konkurentni zahtev
        # u medjuvremenu kreirao order za istu Sagu
        existing_order = db.query(models.Order).filter(
            models.Order.saga_id == order.saga_id
        ).first()

        if existing_order:
            return existing_order

        # Ako IntegrityError nije nastao zbog duplog saga_id,
        # prosledi originalnu gresku
        raise

    db.refresh(new_order)

    return new_order


@app.get("/orders", response_model=list[schemas.OrderResponse])
def get_orders(
    db: Session = Depends(get_db)
):
    orders = db.query(models.Order).all()
    return orders


@app.put("/orders/status", response_model=schemas.OrderResponse)
def update_order_status(
    order_update: schemas.OrderUpdate,
    db: Session = Depends(get_db)
):
    # Zakljucaj order dok se menja njegov status
    order = (
        db.query(models.Order)
        .filter(models.Order.id == order_update.id)
        .with_for_update()
        .first()
    )

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    # Ako je status vec postavljen, operacija je idempotentna
    if order.status == order_update.status:
        return order

    # ne moze PAID ako je bio CANCELLED
    if order.status == "CANCELLED":
        raise HTTPException(
            status_code=409,
            detail="Order already cancelled"
        )

    # Dozvoljavamo PENDING -> PAID
    if order.status != "PENDING" or order_update.status != "PAID":
        raise HTTPException(
            status_code=409,
            detail="Invalid order status transition"
        )

    order.status = "PAID"

    db.commit()
    db.refresh(order)

    return order


@app.post("/cancel", response_model=schemas.OrderResponse)
def cancel_order(
    request: schemas.CancelOrderRequest,
    db: Session = Depends(get_db)
):
    # Zakljucavamo
    order = (
        db.query(models.Order)
        .filter(models.Order.id == request.order_id)
        .with_for_update()
        .first()
    )

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    # Vec je otkazan -> idempotentna kompenzacija
    if order.status == "CANCELLED":
        return order

    # Uspesno placen order vise ne treba otkazivati
    if order.status == "PAID":
        raise HTTPException(
            status_code=409,
            detail="Paid order cannot be cancelled"
        )

    order.status = "CANCELLED"

    db.commit()
    db.refresh(order)

    return order