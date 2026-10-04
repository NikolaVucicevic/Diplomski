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
    #da li je vec rezervisan od iste sage
    existing_reservation = db.query(models.Reservation).filter(
        models.Reservation.saga_id == request.saga_id
    ).first()

    # Ako jeste, ne ponovo
    if existing_reservation:
        return {
            "message": "Product already reserved",
            "product_id": existing_reservation.product_id,
            "quantity": existing_reservation.quantity
        }

    # Pronadji proizvod
    product = db.query(models.Product).filter(
        models.Product.id == request.product_id
    ).first()

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    if product.quantity < request.quantity:
        raise HTTPException(
            status_code=400,
            detail="Not enough products in stock"
        )

    # Smanji stanje
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
    # Pronadji rezervaciju preko saga_id
    reservation = db.query(models.Reservation).filter(
        models.Reservation.saga_id == request.saga_id
    ).first()

    if reservation is None:
        raise HTTPException(
            status_code=404,
            detail="Reservation not found"
        )

    # Ako je vec oslobodjena, ne vracaj quantity ponovo
    if reservation.status == "RELEASED":
        return {
            "message": "Product already released",
            "product_id": reservation.product_id
        }

    product = db.query(models.Product).filter(
        models.Product.id == reservation.product_id
    ).first()

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    # Vrati tacno onu kolicinu koja je bila rezervisana
    product.quantity += reservation.quantity

    # Oznaci rezervaciju kao oslobodjenu
    reservation.status = "RELEASED"

    db.commit()
    db.refresh(product)

    return {
        "message": "Product released",
        "product_id": product.id,
        "quantity": product.quantity
    }