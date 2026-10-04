from pydantic import BaseModel


class OrderCreate(BaseModel):
    saga_id: int
    product_id: int
    quantity: int
    price: float

class OrderUpdate(BaseModel):
    id: int
    status: str


class OrderResponse(BaseModel):
    id: int
    saga_id: int
    product_id: int
    quantity: int
    price: float
    status: str

    model_config = {
        "from_attributes": True
    }

class CancelOrderRequest(BaseModel):
    order_id: int

    model_config = {
        "from_attributes": True
    }