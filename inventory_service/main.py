from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from .database import engine, get_db
from . import models, schemas


models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Inventory Service")


@app.get("/")
def root():
    return {"message": "Inventory Service radi"}


@app.post("/products", response_model=schemas.ProductResponse)
def create_product(
    product: schemas.ProductCreate,
    db: Session = Depends(get_db)
):
    new_product = models.Product(
        name=product.name,
        quantity=product.quantity
    )

    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    return new_product


@app.get("/products", response_model=list[schemas.ProductResponse])
def get_products(db: Session = Depends(get_db)):
    return db.query(models.Product).all()


@app.post("/reserve")
def reserve_product(
    request: schemas.ReserveRequest,
    db: Session = Depends(get_db)
):
    # Zakljucavamo proizvod
    product = (
        db.query(models.Product)
        .filter(models.Product.id == request.product_id)
        .with_for_update()
        .first()
    )

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    # Proveravamp da li je Saga vec rezervisala proizvod
    existing_reservation = db.query(models.Reservation).filter(
        models.Reservation.saga_id == request.saga_id
    ).first()

    if existing_reservation:
        if existing_reservation.status == "RELEASED":
            raise HTTPException(
                status_code=409,
                detail="Reservation already released"
            )

        return {
            "message": "Product already reserved",
            "product_id": existing_reservation.product_id,
            "quantity": existing_reservation.quantity
        }

    # Proveramo dostupnu kolicinu
    if product.quantity < request.quantity:
        raise HTTPException(
            status_code=400,
            detail="Not enough products in stock"
        )

    # Smanjujemo stanje proizvoda
    product.quantity -= request.quantity

    # Kreiramo rezervaciju
    reservation = models.Reservation(
        saga_id=request.saga_id,
        product_id=request.product_id,
        quantity=request.quantity,
        status="RESERVED"
    )

    db.add(reservation)
    db.commit()
    db.refresh(product)

    return {
        "message": "Product reserved",
        "product_id": product.id,
        "remaining_quantity": product.quantity
    }

@app.post("/release")
def release_product(
    request: schemas.ReleaseRequest,
    db: Session = Depends(get_db)
):
    # Treba da pronadjemo rezervaciju preko saga_id
    reservation = db.query(models.Reservation).filter(
        models.Reservation.saga_id == request.saga_id
    ).first()

    if reservation is None:
        raise HTTPException(
            status_code=404,
            detail="Reservation not found"
        )

    # Zakljucavanje proizvoda
    product = (
        db.query(models.Product)
        .filter(models.Product.id == reservation.product_id)
        .with_for_update()
        .first()
    )

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    # Zakljucavanje rezervacije i ponovo status proveravamo
    reservation = (
        db.query(models.Reservation)
        .filter(models.Reservation.saga_id == request.saga_id)
        .populate_existing()
        .with_for_update()
        .first()
    )

    if reservation.status == "RELEASED":
        return {
            "message": "Product already released",
            "product_id": reservation.product_id
        }

    # Azuriramo
    product.quantity += reservation.quantity

    # Oznacavamo rezervaciju kao oslobodjenu
    reservation.status = "RELEASED"

    db.commit()
    db.refresh(product)

    return {
        "message": "Product released",
        "product_id": product.id,
        "quantity": product.quantity
    }