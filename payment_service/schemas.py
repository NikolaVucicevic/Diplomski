from pydantic import BaseModel


class PaymentCreate(BaseModel):
    order_id: int
    amount: float


class PaymentResponse(BaseModel):
    id: int
    order_id: int
    amount: float
    status: str

    model_config = {
        "from_attributes": True
    }