from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

from .database import engine, get_db
from . import models, schemas


models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Payment Service")


@app.get("/")
def root():
    return {"message": "Payment Service radi"}


@app.post("/payments", response_model=schemas.PaymentResponse)
def create_payment(
    payment: schemas.PaymentCreate,
    db: Session = Depends(get_db)
):
    new_payment = models.Payment(
        order_id=payment.order_id,
        amount=payment.amount,
        status="COMPLETED"
    )

    db.add(new_payment)
    db.commit()
    db.refresh(new_payment)

    return new_payment


@app.get("/payments", response_model=list[schemas.PaymentResponse])
def get_payments(db: Session = Depends(get_db)):
    return db.query(models.Payment).all()