from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

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
    new_order = models.Order(
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