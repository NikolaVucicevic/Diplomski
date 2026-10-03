from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from .database import engine, get_db
from . import models, schemas


models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Payment Service")


@app.get("/")
def root():
    return {"message": "Payment Service radi"}


@app.post("/accounts", response_model=schemas.AccountResponse)
def create_account(
    account: schemas.AccountCreate,
    db: Session = Depends(get_db)
):
    new_account = models.Account(
        client_id=account.client_id,
        balance=account.balance
    )

    db.add(new_account)
    db.commit()
    db.refresh(new_account)

    return new_account

@app.get("/accounts/{account_id}", response_model=schemas.AccountResponse)
def get_account(
    account_id: int,
    db: Session = Depends(get_db)
):
    account = db.query(models.Account).filter(
        models.Account.id == account_id
    ).first()

    if account is None:
        raise HTTPException(
            status_code=404,
            detail="Account not found"
        )

    return account


@app.post("/pay", response_model=schemas.PaymentResponse)
def create_payment(
    payment: schemas.PaymentCreate,
    db: Session = Depends(get_db)
):
    account = db.query(models.Account).filter(
        models.Account.id == payment.account_id
    ).first()

    if account is None:
        raise HTTPException(
            status_code=404,
            detail="Account not found"
        )

    if account.balance < payment.amount:
        raise HTTPException(
            status_code=400,
            detail="Insufficient funds"
        )

    account.balance -= payment.amount

    new_payment = models.Payment(
        order_id=payment.order_id,
        account_id=payment.account_id,
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


@app.post("/refund", response_model=schemas.PaymentResponse)
def refund_payment(
    request: schemas.PaymentRefund,
    db: Session = Depends(get_db)
):
    payment = db.query(models.Payment).filter(
        models.Payment.id == request.payment_id
    ).first()

    if payment is None:
        raise HTTPException(
            status_code=404,
            detail="Payment not found"
        )

    if payment.status != "COMPLETED":
        raise HTTPException(
            status_code=400,
            detail="Payment cannot be refunded"
        )

    account = db.query(models.Account).filter(
        models.Account.id == payment.account_id
    ).first()

    if account is None:
        raise HTTPException(
            status_code=404,
            detail="Account not found"
        )

    account.balance += payment.amount
    payment.status = "REFUNDED"

    db.commit()
    db.refresh(payment)

    return payment