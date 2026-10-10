from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session

from . import schemas, models
from .database import engine, get_db
from .http_client import post_with_retry, put_with_retry


models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Saga Orchestrator Service")


@app.get("/")
def root():
    return {"message": "Saga Orchestrator Service radi"}


@app.get("/sagas")
def get_sagas(db: Session = Depends(get_db)):
    sagas = db.query(models.Saga).all()
    return sagas


@app.post("/saga")
def start_saga(
    request: schemas.OrderSagaRequest,
    db: Session = Depends(get_db)
):

    # 0. Kreiramo Sagu
    saga = models.Saga(
        status="STARTED",
        current_step="STARTED"
    )

    db.add(saga)
    db.commit()
    db.refresh(saga)

    saga_id = saga.id

    # 1. Kreiramo order
    order_response = post_with_retry(
        "http://localhost:8001/create",
        json={
            "saga_id": saga_id,
            "product_id": request.product_id,
            "quantity": request.quantity,
            "price": request.price
        }
    )

    if not order_response.is_success:
        saga.status = "FAILED"
        saga.current_step = "ORDER_CREATION_FAILED"
        db.commit()

        raise HTTPException(
            status_code=400,
            detail="Order creation failed"
        )

    order = order_response.json()
    order_id = order["id"]

    # Sacuvamo order_id i trenutno stanje Sage
    saga.order_id = order_id
    saga.status = "IN_PROGRESS"
    saga.current_step = "ORDER_CREATED"
    db.commit()

    # 2. Rezervisemo proizvod
    inventory_response = post_with_retry(
        "http://localhost:8002/reserve",
        json={
            "saga_id": saga_id,
            "product_id": request.product_id,
            "quantity": request.quantity
        }
    )

    if not inventory_response.is_success:

        saga.status = "COMPENSATING"
        saga.current_step = "CANCELLING_ORDER"
        db.commit()

        # Kompenzacija za create order
        cancel_response = post_with_retry(
            "http://localhost:8001/cancel",
            json={
                "order_id": order_id
            }
        )

        if not cancel_response.is_success:
            saga.status = "COMPENSATION_FAILED"
            saga.current_step = "ORDER_CANCEL_FAILED"
            db.commit()

            raise HTTPException(
                status_code=500,
                detail="Inventory reservation failed and order compensation failed"
            )

        saga.status = "COMPENSATED"
        saga.current_step = "ORDER_CANCELLED"
        db.commit()

        raise HTTPException(
            status_code=400,
            detail="Inventory reservation failed"
        )

    saga.current_step = "INVENTORY_RESERVED"
    db.commit()

    # 3. Izvrsavamo placanje
    payment_response = post_with_retry(
        "http://localhost:8003/pay",
        json={
            "saga_id": saga_id,
            "order_id": order_id,
            "account_id": request.account_id,
            "amount": request.price * request.quantity
        }
    )

    if not payment_response.is_success:

        saga.status = "COMPENSATING"
        saga.current_step = "RELEASING_INVENTORY"
        db.commit()

        # Kompenzacija za reserve
        release_response = post_with_retry(
            "http://localhost:8002/release",
            json={
                "saga_id": saga_id
            }
        )

        if not release_response.is_success:
            saga.status = "COMPENSATION_FAILED"
            saga.current_step = "INVENTORY_RELEASE_FAILED"
            db.commit()

            raise HTTPException(
                status_code=500,
                detail="Payment failed and inventory compensation failed"
            )

        saga.current_step = "CANCELLING_ORDER"
        db.commit()

        # Kompenzacija za create order
        cancel_response = post_with_retry(
            "http://localhost:8001/cancel",
            json={
                "order_id": order_id
            }
        )

        if not cancel_response.is_success:
            saga.status = "COMPENSATION_FAILED"
            saga.current_step = "ORDER_CANCEL_FAILED"
            db.commit()

            raise HTTPException(
                status_code=500,
                detail="Payment failed and order compensation failed"
            )

        saga.status = "COMPENSATED"
        saga.current_step = "COMPENSATED"
        db.commit()

        raise HTTPException(
            status_code=400,
            detail="Payment failed"
        )

    saga.current_step = "PAYMENT_COMPLETED"
    db.commit()

    # 4. Menjamo status ordera na PAID
    status_response = put_with_retry(
        "http://localhost:8001/orders/status",
        json={
            "id": order_id,
            "status": "PAID"
        }
    )

    if not status_response.is_success:

        saga.status = "COMPENSATING"
        saga.current_step = "REFUNDING_PAYMENT"
        db.commit()

        # Kompenzacija za payment
        refund_response = post_with_retry(
            "http://localhost:8003/refund",
            json={
                "saga_id": saga_id
            }
        )

        if not refund_response.is_success:
            saga.status = "COMPENSATION_FAILED"
            saga.current_step = "PAYMENT_REFUND_FAILED"
            db.commit()

            raise HTTPException(
                status_code=500,
                detail="Order status update failed and payment compensation failed"
            )

        saga.current_step = "RELEASING_INVENTORY"
        db.commit()

        # Kompenzacija za reserve
        release_response = post_with_retry(
            "http://localhost:8002/release",
            json={
                "saga_id": saga_id
            }
        )

        if not release_response.is_success:
            saga.status = "COMPENSATION_FAILED"
            saga.current_step = "INVENTORY_RELEASE_FAILED"
            db.commit()

            raise HTTPException(
                status_code=500,
                detail="Order status update failed and inventory compensation failed"
            )

        saga.current_step = "CANCELLING_ORDER"
        db.commit()

        # Kompenzacija za create order
        cancel_response = post_with_retry(
            "http://localhost:8001/cancel",
            json={
                "order_id": order_id
            }
        )

        if not cancel_response.is_success:
            saga.status = "COMPENSATION_FAILED"
            saga.current_step = "ORDER_CANCEL_FAILED"
            db.commit()

            raise HTTPException(
                status_code=500,
                detail="Order status update failed and order compensation failed"
            )

        saga.status = "COMPENSATED"
        saga.current_step = "COMPENSATED"
        db.commit()

        raise HTTPException(
            status_code=400,
            detail="Order status update failed"
        )

    # 5. Saga je uspesno zavrsena
    saga.status = "COMPLETED"
    saga.current_step = "COMPLETED"
    db.commit()

    return {
        "saga_id": saga_id,
        "order_id": order_id,
        "status": "PAID"
    }


@app.delete("/test-data/saga/{saga_id}")
def delete_test_saga(
    saga_id: int,
    db: Session = Depends(get_db)
):
    saga = db.query(models.Saga).filter(
        models.Saga.id == saga_id
    ).first()

    if not saga:
        raise HTTPException(
            status_code=404,
            detail="Saga not found"
        )

    db.delete(saga)
    db.commit()

    return {
        "message": "Test saga deleted",
        "saga_id": saga_id
    }
