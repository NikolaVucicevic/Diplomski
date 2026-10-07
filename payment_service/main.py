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
    # Zakljucavamo racun
    account = (
        db.query(models.Account)
        .filter(models.Account.id == payment.account_id)
        .with_for_update()
        .first()
    )

    if account is None:
        raise HTTPException(
            status_code=404,
            detail="Account not found"
        )

    # Proveravamo da li je Saga vec izvrsila placanje
    existing_payment = db.query(models.Payment).filter(
        models.Payment.saga_id == payment.saga_id
    ).first()

    if existing_payment:
        if existing_payment.status == "REFUNDED":
            raise HTTPException(
                status_code=409,
                detail="Payment already refunded"
            )

        return existing_payment

    if account.balance < payment.amount:
        raise HTTPException(
            status_code=400,
            detail="Insufficient funds"
        )

    # Skidamo novac
    account.balance -= payment.amount

    # Kreiramo zapis o placanju
    new_payment = models.Payment(
        saga_id=payment.saga_id,
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
    # Pronalazimo placanje
    payment = db.query(models.Payment).filter(
        models.Payment.saga_id == request.saga_id
    ).first()

    if payment is None:
        raise HTTPException(
            status_code=404,
            detail="Payment not found"
        )

    # Zakljucavamo racun
    account = (
        db.query(models.Account)
        .filter(models.Account.id == payment.account_id)
        .with_for_update()
        .first()
    )

    if account is None:
        raise HTTPException(
            status_code=404,
            detail="Account not found"
        )

    # Zakljucavamo placanje i ponovo ucitaj status
    payment = (
        db.query(models.Payment)
        .filter(models.Payment.saga_id == request.saga_id)
        .populate_existing()
        .with_for_update()
        .first()
    )

    # Ako je novac vec vracen, ne vracaj ponovo
    if payment.status == "REFUNDED":
        return payment

    # Vracamo novac
    account.balance += payment.amount

    # Oznacavamo placanje kao refundirano
    payment.status = "REFUNDED"

    db.commit()
    db.refresh(payment)

    return payment