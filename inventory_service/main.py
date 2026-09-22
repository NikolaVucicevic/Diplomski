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

    product.quantity -= request.quantity

    db.commit()
    db.refresh(product)

    return {
        "message": "Product reserved",
        "product_id": product.id,
        "remaining_quantity": product.quantity
    }